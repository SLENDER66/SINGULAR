import XCTest
@testable import SingularSage

/// Le journal doit être utilisable, honnête, et impossible à réécrire en douce.
@MainActor
final class JournalTests: XCTestCase {

    private var location: URL!

    override func setUp() {
        super.setUp()
        location = FileManager.default.temporaryDirectory
            .appendingPathComponent("journal-\(UUID().uuidString).json")
    }

    override func tearDown() {
        try? FileManager.default.removeItem(at: location)
        super.tearDown()
    }

    private func makeJournal() -> Journal { Journal(location: location) }

    @discardableResult
    private func add(_ journal: Journal, hours: Double = 4, probability: Double = 0.6,
                     days: Int = 14, tier: Tier = .revenus) throws -> Entry {
        try journal.add(title: "Une décision", action: "faire la chose",
                        predicted: "le résultat observable", probability: probability,
                        tier: tier, costHours: hours, horizonDays: days, now: Self.now)
    }

    private static let now = Date(timeIntervalSince1970: 1_789_000_000)

    // MARK: La chaîne

    func testAnOrdinaryJournalVerifies() throws {
        let journal = makeJournal()
        try add(journal, hours: 60)
        try add(journal, hours: 2.5, tier: .stabilite)
        XCTAssertTrue(journal.verify())
    }

    func testResolvingDoesNotBreakTheChain() throws {
        let journal = makeJournal()
        let entry = try add(journal)
        try journal.resolve(entry.id, happened: true, lesson: "ça a marché")
        XCTAssertTrue(journal.verify(), "trancher note la prédiction, il ne la réécrit pas")
    }

    func testARewrittenPredictionBreaksTheChain() throws {
        // La falsification passe par le fichier, comme dans la vraie vie : le
        // journal n'expose aucun moyen de réécrire une entrée, et c'est le
        // point. Quelqu'un qui veut retoucher une prédiction ouvre le JSON.
        let journal = makeJournal()
        try add(journal, probability: 0.6)
        try add(journal)
        XCTAssertTrue(journal.verify())

        var raw = try String(contentsOf: location, encoding: .utf8)
        raw = raw.replacingOccurrences(of: "\"probability\" : 0.6", with: "\"probability\" : 0.05")
        XCTAssertFalse(raw.contains("\"probability\" : 0.6"), "le remplacement n'a rien changé")
        try raw.write(to: location, atomically: true, encoding: .utf8)

        XCTAssertFalse(makeJournal().verify(), "une prédiction retouchée après coup doit se voir")
    }

    func testTheChainSurvivesAReload() throws {
        let first = makeJournal()
        for _ in 0..<3 { try add(first) }
        XCTAssertTrue(makeJournal().verify(), "relire le fichier ne doit pas rompre la chaîne")
        XCTAssertEqual(makeJournal().entries.count, 3)
    }

    // MARK: Les refus

    func testCertaintyIsRefused() {
        let journal = makeJournal()
        XCTAssertThrowsError(try add(journal, probability: 1.0)) { error in
            XCTAssertEqual(error as? Journal.JournalError, .invalidProbability)
        }
        XCTAssertThrowsError(try add(journal, probability: 0.0))
    }

    func testAnUncheckableHorizonIsRefused() {
        XCTAssertThrowsError(try add(makeJournal(), days: 0)) { error in
            XCTAssertEqual(error as? Journal.JournalError, .invalidHorizon)
        }
    }

    func testAnEmptyPredictionIsRefused() {
        let journal = makeJournal()
        XCTAssertThrowsError(try journal.add(title: "A", action: "a", predicted: "   ",
                                             probability: 0.5, tier: .revenus,
                                             costHours: 1, horizonDays: 7))
    }

    func testHistoryIsNotEditable() throws {
        let journal = makeJournal()
        let entry = try add(journal)
        try journal.resolve(entry.id, happened: true)
        XCTAssertThrowsError(try journal.resolve(entry.id, happened: false)) { error in
            XCTAssertEqual(error as? Journal.JournalError, .alreadyResolved(entry.id))
        }
    }

    // MARK: Les comptes

    func testBrierScoresTheForecastNotTheOutcome() throws {
        let journal = makeJournal()
        let entry = try add(journal, probability: 0.9)
        let resolved = try journal.resolve(entry.id, happened: false)
        XCTAssertEqual(try XCTUnwrap(resolved.brierScore), 0.81, accuracy: 1e-9)
    }

    func testOverdueIsCountedInWholeDays() throws {
        let journal = makeJournal()
        let entry = try add(journal, days: 7)
        let elevenDaysLater = Self.now.addingTimeInterval(11 * 86_400)
        XCTAssertEqual(entry.overdueDays(at: elevenDaysLater), 4)
        XCTAssertEqual(entry.overdueDays(at: Self.now), 0, "jamais négatif")
        XCTAssertEqual(journal.due(at: elevenDaysLater).count, 1)
        XCTAssertTrue(journal.due(at: Self.now).isEmpty)
    }
}
