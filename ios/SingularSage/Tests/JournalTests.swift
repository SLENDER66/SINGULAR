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

        // Relire, modifier, réécrire en JSON plutôt que par remplacement de
        // texte : l'espacement produit par JSONEncoder n'est pas un contrat, et
        // un test qui échoue parce que Foundation met un espace avant les deux
        // points ferait perdre un aller-retour pour rien.
        let data = try Data(contentsOf: location)
        var rows = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [[String: Any]])
        XCTAssertEqual(rows.count, 2)
        rows[0]["probability"] = 0.05
        try JSONSerialization.data(withJSONObject: rows).write(to: location)

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

    // MARK: Un fichier illisible n'est pas un journal vide

    func testAnUnreadableJournalRefusesToBeOverwritten() throws {
        // Le pire scénario possible pour cette app : des années de décisions
        // remplacées en silence par une décision neuve, parce qu'une lecture
        // ratée rendait « rien » et que « rien » ressemble à un premier
        // lancement.
        let first = makeJournal()
        try add(first)
        try add(first)
        let original = try Data(contentsOf: location)

        try Data("ceci n'est plus du JSON".utf8).write(to: location)
        let broken = makeJournal()

        XCTAssertNotNil(broken.loadFailure, "un fichier illisible doit être signalé")
        XCTAssertTrue(broken.entries.isEmpty)
        XCTAssertThrowsError(try add(broken)) { error in
            guard case .unreadable = error as? Journal.JournalError else {
                return XCTFail("l'écriture doit être refusée, pas silencieuse : \(error)")
            }
        }
        XCTAssertEqual(try Data(contentsOf: location).count,
                       "ceci n'est plus du JSON".utf8.count,
                       "le fichier ne doit surtout pas avoir été réécrit")
        XCTAssertNotEqual(original, try Data(contentsOf: location))
    }

    func testAMissingFileIsAFirstLaunchNotAFailure() throws {
        let journal = makeJournal()
        XCTAssertNil(journal.loadFailure, "l'absence de fichier est le cas normal du premier lancement")
        XCTAssertNoThrow(try add(journal))
    }

    func testAReadableJournalRestoredAfterAFailureWritesAgain() throws {
        /// La panne doit être réversible : remettre un fichier valide suffit.
        let first = makeJournal()
        try add(first)
        let good = try Data(contentsOf: location)

        try Data("cassé".utf8).write(to: location)
        XCTAssertNotNil(makeJournal().loadFailure)

        try good.write(to: location)
        let restored = makeJournal()
        XCTAssertNil(restored.loadFailure)
        XCTAssertEqual(restored.entries.count, 1)
        XCTAssertNoThrow(try add(restored))
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
