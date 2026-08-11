// pack-hadith - builds the app-ready hadith packs (.hpk) from this repo's book JSONs.
//
//   tools/pack/build.sh                 # compile, pack, verify the invariants, write the manifest
//
// Everything that CAN be decided ahead of time is decided here, once, so the app never spends a
// device's battery on it:
//
//   - the whitespace cleanup (hard-wrapped lines, doubled spaces, tabs, no-break spaces)
//   - the Arabic and English SEARCH FOLDS, for every hadith and every chapter name, so a keystroke
//     on the device is a byte compare and never a normalization pass
//   - each chapter's ROW RANGE, so opening a chapter is a slice instead of a scan of the whole book
//   - the DAILY-CARD flags (short enough, and free of the blocked words), so Hadith of the Day never
//     reads a book's text to choose one
//   - the block layout and compression, so reading one chapter decompresses ~one 256 KB block
//
// Fields the app never reads (bookId, the book-level id, chapter bookId, the empty metadata
// introductions) are dropped entirely.
//
// The format is specified in docs/04-hpk-format.md; Al-Islam-iOS/iPhone/Hadith/HadithPack.swift reads it back.

import Foundation
import Compression

// MARK: - Small binary writer

struct ByteWriter {
    private(set) var data = Data()

    mutating func u8(_ value: Int) { data.append(UInt8(truncatingIfNeeded: value)) }

    mutating func u16(_ value: Int) {
        var little = UInt16(value).littleEndian
        withUnsafeBytes(of: &little) { data.append(contentsOf: $0) }
    }

    mutating func u32(_ value: Int) {
        var little = UInt32(truncatingIfNeeded: value).littleEndian
        withUnsafeBytes(of: &little) { data.append(contentsOf: $0) }
    }

    mutating func u64(_ value: UInt64) {
        var little = value.littleEndian
        withUnsafeBytes(of: &little) { data.append(contentsOf: $0) }
    }

    mutating func i32(_ value: Int) {
        var little = Int32(truncatingIfNeeded: value).littleEndian
        withUnsafeBytes(of: &little) { data.append(contentsOf: $0) }
    }

    /// A length-prefixed UTF-8 string.
    mutating func string(_ value: String) {
        let bytes = Array(value.utf8)
        u32(bytes.count)
        data.append(contentsOf: bytes)
    }

    mutating func raw(_ bytes: Data) { data.append(bytes) }
}

// MARK: - Compression

/// Pack codecs, mirrored by `HadithPack.Codec`.
enum Codec: UInt8 {
    case lzfse = 1
    case lzma = 2

    var algorithm: compression_algorithm {
        switch self {
        case .lzfse: return COMPRESSION_LZFSE
        case .lzma: return COMPRESSION_LZMA
        }
    }
}

func compress(_ data: Data, _ codec: Codec) -> Data {
    guard !data.isEmpty else { return Data() }
    let capacity = data.count + 4096
    let destination = UnsafeMutablePointer<UInt8>.allocate(capacity: capacity)
    defer { destination.deallocate() }
    let written = data.withUnsafeBytes { source in
        compression_encode_buffer(
            destination, capacity,
            source.bindMemory(to: UInt8.self).baseAddress!, data.count,
            nil, codec.algorithm
        )
    }
    guard written > 0 else {
        FileHandle.standardError.write(Data("compression failed for a \(data.count)-byte section\n".utf8))
        exit(1)
    }
    return Data(bytes: destination, count: written)
}

// MARK: - Source cleanup

extension String {
    /// The dataset carries hard-wrapped lines, doubled spaces, tabs, and no-break spaces. Deliberate
    /// paragraph breaks (blank lines) survive as one "\n\n"; every other whitespace run collapses to a
    /// single space. This used to run on every device on every decode; now it runs once, here.
    var cleanedHadithText: String {
        guard contains("\n") || contains("  ") || contains("\t") || contains("\r") || contains("\u{00A0}") else {
            return self
        }
        var text = self
            .replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\r", with: "\n")
            .replacingOccurrences(of: "\t", with: " ")
            .replacingOccurrences(of: "\u{00A0}", with: " ")
        text = text.replacingOccurrences(of: "[ ]*\\n[ ]*", with: "\n", options: .regularExpression)
        text = text.replacingOccurrences(of: "\\n{2,}", with: "\u{2029}", options: .regularExpression)
        text = text.replacingOccurrences(of: "\n", with: " ")
        text = text.replacingOccurrences(of: " {2,}", with: " ", options: .regularExpression)
        text = text.replacingOccurrences(of: " ?\u{2029} ?", with: "\n\n", options: .regularExpression)
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

/// Shama'il Muhammadiyah squeezes a sub-chapter in as the FLOAT id `8.2`, on the chapter and on its
/// hadiths. Truncating collides with chapter 8, so fractional ids map to a stable synthetic integer.
func normalizedChapterId(_ raw: Double) -> Int {
    raw == raw.rounded(.down) ? Int(raw) : 1000 + Int((raw * 10).rounded())
}

func chapterId(_ value: Any?) -> Int {
    if let int = value as? Int { return int }
    if let number = value as? NSNumber { return normalizedChapterId(number.doubleValue) }
    if let string = value as? String, let double = Double(string) { return normalizedChapterId(double) }
    return 0
}

// MARK: - Daily-card policy

/// The blocked-word list, read from `daily-blocked-words.txt` beside this file. See the header there:
/// the app keeps the canonical copy, and a fingerprint mismatch makes the app recheck rather than
/// trust these flags - so an out-of-sync list costs speed, never correctness.
struct DailyFilter {
    let words: Set<String>
    let fingerprint: UInt64

    init(url: URL) throws {
        let lines = try String(contentsOf: url, encoding: .utf8).components(separatedBy: .newlines)
        var set = Set<String>()
        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            guard !trimmed.isEmpty, !trimmed.hasPrefix("#") else { continue }
            set.insert(trimmed.lowercased())
        }
        words = set
        fingerprint = HadithFold.wordListFingerprint(set)
    }

    /// Whole-word check, never substrings - "hit" as a substring would block every "white".
    func containsBlockedWord(_ text: String) -> Bool {
        text.lowercased()
            .split(whereSeparator: { !$0.isLetter })
            .contains { words.contains(String($0)) }
    }
}

/// Per-hadith flags, mirrored by `HadithPack.Row.flags`.
enum RowFlag {
    /// Short enough for a daily card, in both scripts, with English text present. Objective, derived
    /// from the data alone.
    static let dailyLength: Int = 1 << 0
    /// Free of the daily-card blocked words. Policy, and fingerprinted.
    static let dailyGentle: Int = 1 << 1
}

/// The daily card never carries a page-long hadith.
let dailyMaxCharacters = 220

// MARK: - Book layout

/// The books to pack, in the app's catalog order, with the folder each lives in.
let books: [(slug: String, folder: String)] = [
    ("bukhari", "the_9_books"), ("muslim", "the_9_books"), ("ibnmajah", "the_9_books"),
    ("abudawud", "the_9_books"), ("tirmidhi", "the_9_books"), ("nasai", "the_9_books"),
    ("malik", "the_9_books"), ("ahmed", "the_9_books"), ("darimi", "the_9_books"),
    ("qudsi40", "forties"), ("nawawi40", "forties"), ("shahwaliullah40", "forties"),
    ("aladab_almufrad", "other_books"), ("shamail_muhammadiyah", "other_books"),
    ("riyad_assalihin", "other_books"), ("mishkat_almasabih", "other_books"),
    ("bulugh_almaram", "other_books"),
]

/// Target raw bytes of DISPLAY text per block. Measured across 64K/128K/256K/512K/1M: the ratio keeps
/// improving with size (the compressor gets a longer window), but so does the cost of touching one
/// hadith. 256K is the knee - it gives up ~1.5 MB against 1 MB blocks and keeps a single block's LZMA
/// decode near a millisecond, so opening a chapter is 1-3 blocks and a few ms.
let blockTargetBytes = (ProcessInfo.processInfo.environment["HPK_BLOCK"].flatMap { Int($0) } ?? 256) * 1024

/// Display text is decompressed a block at a time while reading, and the reader caches it - LZMA's
/// extra saving (12.8 MB vs ~19 MB for the same text) is worth its ~170 MB/s decode there, because a
/// read touches one block. The search folds are the opposite case: a query scans EVERY block of every
/// book, 48 MB of it, so those take LZFSE at ~1.6 GB/s and pay 2.4 MB for the privilege.
let textCodec = Codec(rawValue: UInt8(ProcessInfo.processInfo.environment["HPK_TEXT"].flatMap { Int($0) } ?? 2))!
let searchCodec = Codec(rawValue: UInt8(ProcessInfo.processInfo.environment["HPK_SEARCH"].flatMap { Int($0) } ?? 1))!
let eagerCodec = Codec.lzma

let magic: UInt32 = 0x4B50_4448   // "HDPK" little-endian
// Version 3 widened the per-row record from 15 to 20 bytes: u32 citation base + u8 citation
// suffix, the standard sunnah.com number ("2950", "8a") that tools/add_citations.py attached.
// Version 4 added a FOURTH display string per hadith: the scholar gradings from
// tools/add_grades.py, encoded "name\u{1F}grade" joined by "\u{1E}", empty when ungraded.
let formatVersion = 4

// MARK: - Pack one book

struct PackResult {
    let slug: String
    let sourceBytes: Int
    let packBytes: Int
    let chapters: Int
    let hadiths: Int
    let dailyCandidates: Int
    let blocks: Int
    let sha256: String
}

func pack(slug: String, folder: String, sourceDirectory: URL, outputDirectory: URL,
          filter: DailyFilter) throws -> PackResult {
    let sourceURL = sourceDirectory.appendingPathComponent(folder).appendingPathComponent("\(slug).json")
    let sourceData = try Data(contentsOf: sourceURL)
    guard let root = try JSONSerialization.jsonObject(with: sourceData) as? [String: Any],
          let metadata = root["metadata"] as? [String: Any],
          let rawChapters = root["chapters"] as? [[String: Any]],
          let rawHadiths = root["hadiths"] as? [[String: Any]] else {
        throw Failure("\(slug).json is not in the expected shape")
    }

    let arabicMeta = metadata["arabic"] as? [String: Any] ?? [:]
    let englishMeta = metadata["english"] as? [String: Any] ?? [:]

    // --- Hadiths, cleaned and folded ---
    struct Hadith {
        let id: Int
        let idInBook: Int
        let chapterId: Int
        let citationBase: Int      // 0 = no standard citation exists for this row
        let citationSuffix: Int    // 0 = none, 1...26 = "a"..."z" (Sahih Muslim 8a)
        let arabic: String
        let narrator: String
        let text: String
        let grades: String         // "name\u{1F}grade" joined by "\u{1E}"; empty when ungraded
        let foldArabic: String
        let foldEnglish: String
        let flags: Int
    }
    let hadiths: [Hadith] = try rawHadiths.map { raw in
        let english = raw["english"] as? [String: Any] ?? [:]
        let arabic = (raw["arabic"] as? String ?? "").cleanedHadithText
        let narrator = (english["narrator"] as? String ?? "").cleanedHadithText
        let text = (english["text"] as? String ?? "").cleanedHadithText

        // The scholar gradings, one "name\u{1F}grade" per verdict. Where scholars disagree the
        // data keeps every verdict (docs/03-gradings.md), so the encoding does too. The strings
        // ride as display text, verbatim - they are 2,358 distinct nuanced verdicts, not a scale.
        let grades = ((english["grades"] as? [[String: Any]]) ?? []).compactMap { g -> String? in
            guard let grade = (g["grade"] as? String)?.trimmingCharacters(in: .whitespaces),
                  !grade.isEmpty else { return nil }
            let name = (g["name"] as? String ?? "").trimmingCharacters(in: .whitespaces)
            return name + "\u{1F}" + grade
        }.joined(separator: "\u{1E}")

        var flags = 0
        if arabic.count <= dailyMaxCharacters, text.count <= dailyMaxCharacters, !text.isEmpty {
            flags |= RowFlag.dailyLength
        }
        if !filter.containsBlockedWord(text + " " + narrator) {
            flags |= RowFlag.dailyGentle
        }

        // The standard citation, "2950" or "8a" - attached by tools/add_citations.py, absent
        // where sunnah.com has no collection-level number (Malik, most of Bulugh al-Maram).
        var citationBase = 0
        var citationSuffix = 0
        if let citation = raw["citation"] as? String, !citation.isEmpty {
            var digits = citation
            if let last = citation.last, last.isLetter {
                guard let ascii = last.asciiValue, (97...122).contains(ascii) else {
                    throw Failure("\(slug): citation \"\(citation)\" has a non a-z suffix")
                }
                citationSuffix = Int(ascii - 96)
                digits = String(citation.dropLast())
            }
            guard let base = Int(digits), base > 0 else {
                throw Failure("\(slug): citation \"\(citation)\" is not <digits>[a-z]")
            }
            citationBase = base
        }

        return Hadith(
            id: raw["id"] as? Int ?? 0,
            idInBook: raw["idInBook"] as? Int ?? 0,
            chapterId: chapterId(raw["chapterId"]),
            citationBase: citationBase, citationSuffix: citationSuffix,
            arabic: arabic, narrator: narrator, text: text, grades: grades,
            foldArabic: HadithFold.arabic(arabic),
            // The English fold covers the narration AND its narrator, the one field pair English
            // search has always matched against.
            foldEnglish: HadithFold.english(text + "\n" + narrator),
            flags: flags
        )
    }

    // --- Chapters, with the row range each one owns ---
    // Every book in this repo lays its hadiths out in chapter order, one unbroken run per chapter, so
    // a chapter is a SLICE of the row table rather than a filter over it. That is an invariant of the
    // data, not an assumption: it is checked here, and packing fails loudly if a future update breaks
    // it (the app would otherwise show a chapter the wrong hadiths).
    struct Chapter {
        let id: Int
        let arabic: String
        let english: String
        let foldArabic: String
        let foldEnglish: String
        let firstRow: Int
        let rowCount: Int
    }

    var rowsByChapter: [Int: (first: Int, count: Int)] = [:]
    var order: [Int] = []
    for (row, hadith) in hadiths.enumerated() {
        if let existing = rowsByChapter[hadith.chapterId] {
            guard existing.first + existing.count == row else {
                throw Failure("\(slug): chapter \(hadith.chapterId) is not contiguous (row \(row) "
                              + "follows a run that ended at \(existing.first + existing.count - 1)). "
                              + "The pack format stores chapters as row ranges; it must be extended "
                              + "to an explicit row list before this data can ship.")
            }
            rowsByChapter[hadith.chapterId] = (existing.first, existing.count + 1)
        } else {
            rowsByChapter[hadith.chapterId] = (row, 1)
            order.append(hadith.chapterId)
        }
    }

    let chapters: [Chapter] = try rawChapters.map { raw in
        let id = chapterId(raw["id"])
        let arabic = (raw["arabic"] as? String ?? "").cleanedHadithText
        let english = (raw["english"] as? String ?? "").cleanedHadithText
        guard let range = rowsByChapter[id] else {
            throw Failure("\(slug): chapter \(id) has no hadiths, which the app's chapter rows assume")
        }
        return Chapter(
            id: id, arabic: arabic, english: english,
            foldArabic: HadithFold.arabic(arabic), foldEnglish: HadithFold.english(english),
            firstRow: range.first, rowCount: range.count
        )
    }
    guard chapters.reduce(0, { $0 + $1.rowCount }) == hadiths.count else {
        throw Failure("\(slug): the chapter ranges do not cover every hadith")
    }

    // --- Block boundaries: runs of rows whose display text is about `blockTargetBytes` ---
    var blockRanges: [Range<Int>] = []
    var start = 0
    var accumulated = 0
    for (row, hadith) in hadiths.enumerated() {
        accumulated += hadith.arabic.utf8.count + hadith.narrator.utf8.count + hadith.text.utf8.count
            + hadith.grades.utf8.count + 16
        if accumulated >= blockTargetBytes {
            blockRanges.append(start..<(row + 1))
            start = row + 1
            accumulated = 0
        }
    }
    if start < hadiths.count { blockRanges.append(start..<hadiths.count) }
    if blockRanges.isEmpty { blockRanges.append(0..<0) }
    guard blockRanges.count <= Int(UInt16.max) else {
        throw Failure("\(slug): too many blocks for a UInt16 index")
    }

    var blockIndexByRow = [Int](repeating: 0, count: hadiths.count)
    for (index, range) in blockRanges.enumerated() {
        for row in range { blockIndexByRow[row] = index }
    }

    // --- Eager section: metadata, chapters, and the id table ---
    var eager = ByteWriter()
    eager.string(arabicMeta["title"] as? String ?? "")
    eager.string(arabicMeta["author"] as? String ?? "")
    eager.string(englishMeta["title"] as? String ?? "")
    eager.string(englishMeta["author"] as? String ?? "")
    eager.u32(chapters.count)
    for chapter in chapters {
        eager.i32(chapter.id)
        eager.u32(chapter.firstRow)
        eager.u32(chapter.rowCount)
        eager.string(chapter.arabic)
        eager.string(chapter.english)
        eager.string(chapter.foldArabic)
        eager.string(chapter.foldEnglish)
    }
    eager.u32(hadiths.count)
    for (row, hadith) in hadiths.enumerated() {
        eager.u32(hadith.id)
        eager.u32(hadith.idInBook)
        eager.i32(hadith.chapterId)
        eager.u32(hadith.citationBase)
        eager.u8(hadith.citationSuffix)
        eager.u16(blockIndexByRow[row])
        eager.u8(hadith.flags)
    }
    let eagerRaw = eager.data
    let eagerCompressed = compress(eagerRaw, eagerCodec)

    // --- Block payloads ---
    struct BlockPayload {
        let firstRow: Int
        let text: Data
        let textRaw: Int
        let search: Data
        let searchRaw: Int
    }

    let payloads: [BlockPayload] = blockRanges.map { range in
        // Display: the block's strings back to back, each length-prefixed, FOUR per hadith in row
        // order - the reader splits the whole block once and indexes it by (row - firstRow) * 4.
        var text = ByteWriter()
        for row in range {
            text.string(hadiths[row].arabic)
            text.string(hadiths[row].narrator)
            text.string(hadiths[row].text)
            text.string(hadiths[row].grades)
        }

        // Search: the folds, Arabic section then English section, each record NUL-terminated so a
        // match can never straddle two hadiths. Lengths up front give offset -> row without a scan.
        var search = ByteWriter()
        let rows = Array(range)
        let arabicBytes = rows.map { Array(hadiths[$0].foldArabic.utf8) }
        let englishBytes = rows.map { Array(hadiths[$0].foldEnglish.utf8) }
        search.u32(rows.count)
        search.u32(arabicBytes.reduce(0) { $0 + $1.count + 1 })
        for bytes in arabicBytes { search.u32(bytes.count) }
        for bytes in englishBytes { search.u32(bytes.count) }
        for bytes in arabicBytes { search.raw(Data(bytes)); search.u8(0) }
        for bytes in englishBytes { search.raw(Data(bytes)); search.u8(0) }

        return BlockPayload(
            firstRow: range.lowerBound,
            text: compress(text.data, textCodec), textRaw: text.data.count,
            search: compress(search.data, searchCodec), searchRaw: search.data.count
        )
    }

    // --- Assemble the file ---
    let headerSize = 48
    let blockTableSize = payloads.count * 28
    var out = ByteWriter()
    out.u32(Int(magic))
    out.u16(formatVersion)
    out.u8(Int(eagerCodec.rawValue))
    out.u8(Int(textCodec.rawValue))
    out.u8(Int(searchCodec.rawValue))
    out.u8(0)
    out.u16(payloads.count)
    out.u32(chapters.count)
    out.u32(hadiths.count)
    let eagerOffset = headerSize + blockTableSize
    out.u32(eagerOffset)
    out.u32(eagerCompressed.count)
    out.u32(eagerRaw.count)
    out.u64(HadithFold.foldFingerprint)
    out.u64(filter.fingerprint)

    var cursor = eagerOffset + eagerCompressed.count
    var offsets: [(text: Int, search: Int)] = []
    for payload in payloads {
        offsets.append((cursor, cursor + payload.text.count))
        cursor += payload.text.count + payload.search.count
    }
    for (index, payload) in payloads.enumerated() {
        out.u32(payload.firstRow)
        out.u32(offsets[index].text)
        out.u32(payload.text.count)
        out.u32(payload.textRaw)
        out.u32(offsets[index].search)
        out.u32(payload.search.count)
        out.u32(payload.searchRaw)
    }
    out.raw(eagerCompressed)
    for payload in payloads {
        out.raw(payload.text)
        out.raw(payload.search)
    }

    let outputURL = outputDirectory.appendingPathComponent("\(slug).hpk")
    try out.data.write(to: outputURL, options: .atomic)

    let candidates = hadiths.filter {
        $0.flags & RowFlag.dailyLength != 0 && $0.flags & RowFlag.dailyGentle != 0
    }.count

    return PackResult(
        slug: slug, sourceBytes: sourceData.count, packBytes: out.data.count,
        chapters: chapters.count, hadiths: hadiths.count, dailyCandidates: candidates,
        blocks: payloads.count, sha256: sha256(out.data)
    )
}

// MARK: - Helpers

struct Failure: Error, CustomStringConvertible {
    let description: String
    init(_ description: String) { self.description = description }
}

/// SHA-256 without importing CryptoKit, so this tool builds with nothing but the toolchain.
func sha256(_ data: Data) -> String {
    var h: [UInt32] = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                       0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]
    let k: [UInt32] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
        0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
        0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
        0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
        0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
        0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
        0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]
    var message = [UInt8](data)
    let bitLength = UInt64(message.count) * 8
    message.append(0x80)
    while message.count % 64 != 56 { message.append(0) }
    for shift in stride(from: 56, through: 0, by: -8) {
        message.append(UInt8(truncatingIfNeeded: bitLength >> UInt64(shift)))
    }
    for chunk in stride(from: 0, to: message.count, by: 64) {
        var w = [UInt32](repeating: 0, count: 64)
        for i in 0..<16 {
            let base = chunk + i * 4
            w[i] = (UInt32(message[base]) << 24) | (UInt32(message[base + 1]) << 16)
                 | (UInt32(message[base + 2]) << 8) | UInt32(message[base + 3])
        }
        for i in 16..<64 {
            let s0 = (w[i-15] >> 7 | w[i-15] << 25) ^ (w[i-15] >> 18 | w[i-15] << 14) ^ (w[i-15] >> 3)
            let s1 = (w[i-2] >> 17 | w[i-2] << 15) ^ (w[i-2] >> 19 | w[i-2] << 13) ^ (w[i-2] >> 10)
            w[i] = w[i-16] &+ s0 &+ w[i-7] &+ s1
        }
        var (a, b, c, d, e, f, g, hh) = (h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7])
        for i in 0..<64 {
            let s1 = (e >> 6 | e << 26) ^ (e >> 11 | e << 21) ^ (e >> 25 | e << 7)
            let ch = (e & f) ^ (~e & g)
            let temp1 = hh &+ s1 &+ ch &+ k[i] &+ w[i]
            let s0 = (a >> 2 | a << 30) ^ (a >> 13 | a << 19) ^ (a >> 22 | a << 10)
            let maj = (a & b) ^ (a & c) ^ (b & c)
            let temp2 = s0 &+ maj
            hh = g; g = f; f = e; e = d &+ temp1
            d = c; c = b; b = a; a = temp1 &+ temp2
        }
        h[0] = h[0] &+ a; h[1] = h[1] &+ b; h[2] = h[2] &+ c; h[3] = h[3] &+ d
        h[4] = h[4] &+ e; h[5] = h[5] &+ f; h[6] = h[6] &+ g; h[7] = h[7] &+ hh
    }
    return h.map { String(format: "%08x", $0) }.joined()
}

func column(_ text: String, _ width: Int) -> String {
    text.count >= width ? text : text + String(repeating: " ", count: width - text.count)
}

func rightColumn(_ text: String, _ width: Int) -> String {
    text.count >= width ? text : String(repeating: " ", count: width - text.count) + text
}

// MARK: - Main

@main
struct PackHadith {
    static func main() throws {
        let arguments = CommandLine.arguments
        guard arguments.count == 4 else {
            print("usage: pack-hadith <db/by_book dir> <output dir> <daily-blocked-words.txt>")
            exit(2)
        }
        let sourceDirectory = URL(fileURLWithPath: arguments[1])
        let outputDirectory = URL(fileURLWithPath: arguments[2])
        let filter = try DailyFilter(url: URL(fileURLWithPath: arguments[3]))
        try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)

        var results: [PackResult] = []
        print(column("book", 24) + rightColumn("json", 10) + rightColumn("pack", 10)
              + rightColumn("ratio", 8) + rightColumn("hadiths", 9) + rightColumn("daily", 8)
              + rightColumn("blocks", 8))
        for book in books {
            let result = try pack(slug: book.slug, folder: book.folder,
                                  sourceDirectory: sourceDirectory, outputDirectory: outputDirectory,
                                  filter: filter)
            results.append(result)
            print(column(result.slug, 24)
                  + rightColumn(String(format: "%.2fM", Double(result.sourceBytes) / 1e6), 10)
                  + rightColumn(String(format: "%.2fM", Double(result.packBytes) / 1e6), 10)
                  + rightColumn(String(format: "%.2fx", Double(result.sourceBytes) / Double(max(result.packBytes, 1))), 8)
                  + rightColumn("\(result.hadiths)", 9)
                  + rightColumn("\(result.dailyCandidates)", 8)
                  + rightColumn("\(result.blocks)", 8))
        }
        let totalSource = results.reduce(0) { $0 + $1.sourceBytes }
        let totalPack = results.reduce(0) { $0 + $1.packBytes }
        let totalHadiths = results.reduce(0) { $0 + $1.hadiths }
        let totalChapters = results.reduce(0) { $0 + $1.chapters }
        let totalDaily = results.reduce(0) { $0 + $1.dailyCandidates }
        print(column("TOTAL", 24)
              + rightColumn(String(format: "%.2fM", Double(totalSource) / 1e6), 10)
              + rightColumn(String(format: "%.2fM", Double(totalPack) / 1e6), 10)
              + rightColumn(String(format: "%.2fx", Double(totalSource) / Double(max(totalPack, 1))), 8)
              + rightColumn("\(totalHadiths)", 9)
              + rightColumn("\(totalDaily)", 8))
        print("\(totalChapters) chapters, \(totalHadiths) hadiths, \(totalDaily) daily-card candidates")
        print(String(format: "fold fingerprint %016llx, blocked-word fingerprint %016llx",
                     HadithFold.foldFingerprint, filter.fingerprint))

        // The manifest records exactly what shipped: sizes, shapes, and a checksum per pack.
        var manifest: [String: Any] = [
            "formatVersion": formatVersion,
            "foldFingerprint": String(format: "%016llx", HadithFold.foldFingerprint),
            "blockedWordFingerprint": String(format: "%016llx", filter.fingerprint),
            "blockTargetBytes": blockTargetBytes,
            "textCodec": textCodec == .lzma ? "lzma" : "lzfse",
            "searchCodec": searchCodec == .lzma ? "lzma" : "lzfse",
            "totalChapters": totalChapters,
            "totalHadiths": totalHadiths,
            "totalPackBytes": totalPack,
        ]
        manifest["books"] = results.map { result in
            [
                "slug": result.slug, "bytes": result.packBytes, "sourceBytes": result.sourceBytes,
                "chapters": result.chapters, "hadiths": result.hadiths,
                "dailyCandidates": result.dailyCandidates, "blocks": result.blocks,
                "sha256": result.sha256,
            ] as [String: Any]
        }
        let manifestURL = outputDirectory.appendingPathComponent("manifest.json")
        let json = try JSONSerialization.data(withJSONObject: manifest,
                                              options: [.prettyPrinted, .sortedKeys])
        try json.write(to: manifestURL, options: .atomic)
        print("manifest: \(manifestURL.path)")
    }
}
