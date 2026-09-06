import XCTest
@testable import SingularSage

/// Le port doit dire exactement ce que dit le moteur de référence.
///
/// La Notice vit deux fois : en Python dans le dépôt, et ici sur le téléphone.
/// Deux implémentations de la même règle divergent au premier oubli, et une
/// divergence ici ne plante pas — elle donne un conseil légèrement faux, tous
/// les matins, sans rien dire.
///
/// `notice_vectors.json` est produit par `tools/generate_notice_vectors.py`
/// depuis le moteur Python, lui-même couvert par sa propre suite. Ce test
/// rejoue les mêmes journaux et exige les mêmes phrases, mot pour mot. Un
/// seuil déplacé, un accord oublié, une observation qui ne se déclenche plus :
/// le test nomme le cas et montre les deux textes.
///
/// C'est le premier test à lancer après avoir ouvert le projet. S'il passe, le
/// cœur de l'app fait ce qu'il est censé faire.
@MainActor
final class NoticeVectorTests: XCTestCase {

    // MARK: Les vecteurs, tels qu'ils sont écrits

    struct VectorFile: Decodable {
        let origin: String
        let cases: [Case]
    }

    struct Case: Decodable {
        let name: String
        let why: String
        let at: String
        /// L'intégrité que le moteur de référence avait sous les yeux.
        ///
        /// Le moteur d'observation ne calcule pas l'intégrité, il la reçoit :
        /// c'est un paramètre de `build`. Le vecteur la transmet donc telle
        /// quelle, plutôt que de faire casser un fichier au test. Que
        /// `verify()` détecte réellement une chaîne rompue est une autre
        /// question, et `JournalTests` la traite sur un vrai fichier retouché.
        let chainIntact: Bool
        let entries: [VectorEntry]
        let expected: Expectation

        enum CodingKeys: String, CodingKey {
            case name, why, at, entries, expected
            case chainIntact = "chain_intact"
        }
    }

    struct VectorEntry: Decodable {
        let title: String
        let action: String
        let predicted: String
        let probability: Double
        let tier: String
        let costHours: Double
        let horizonDays: Int
        let createdOffsetDays: Int
        let resolved: Bool?

        enum CodingKeys: String, CodingKey {
            case title, action, predicted, probability, tier, resolved
            case costHours = "cost_hours"
            case horizonDays = "horizon_days"
            case createdOffsetDays = "created_offset_days"
        }
    }

    struct Expectation: Decodable {
        let headline: String
        let severity: String
        let items: [ExpectedItem]
    }

    struct ExpectedItem: Decodable {
        let severity: String
        let title: String
        let detail: String
    }

    // MARK: Le rejeu

    func testEveryVectorMatchesThePortedEngine() throws {
        let file = try loadVectors()
        let origin = try XCTUnwrap(ISO8601DateFormatter.singular.date(from: file.origin))
        XCTAssertFalse(file.cases.isEmpty, "aucun vecteur chargé : le fichier est-il dans le bundle de test ?")

        for testCase in file.cases {
            let journal = try makeJournal(from: testCase, origin: origin)
            let moment = try XCTUnwrap(ISO8601DateFormatter.singular.date(from: testCase.at))
            let notice = NoticeEngine.build(entries: journal.entries, at: moment,
                                            chainIntact: testCase.chainIntact)

            // Le journal rejoué, lui, est toujours écrit à travers l'API : il
            // doit se vérifier, quelle que soit l'intégrité que le vecteur
            // demande de simuler.
            XCTAssertTrue(journal.verify(), "\(testCase.name) : le journal rejoué doit être cohérent")
            XCTAssertEqual(notice.headline, testCase.expected.headline,
                           "\(testCase.name) — \(testCase.why)")
            XCTAssertEqual(notice.severity.rawValue, testCase.expected.severity, testCase.name)
            XCTAssertEqual(notice.items.count, testCase.expected.items.count,
                           "\(testCase.name) : \(notice.items.map(\.title)) au lieu de "
                           + "\(testCase.expected.items.map(\.title))")

            for (produced, expected) in zip(notice.items, testCase.expected.items) {
                XCTAssertEqual(produced.severity.rawValue, expected.severity, testCase.name)
                XCTAssertEqual(produced.title, expected.title, testCase.name)
                XCTAssertEqual(produced.detail, expected.detail, testCase.name)
            }
        }
    }

    /// Un fichier de vecteurs absent ferait passer la suite en ne testant rien.
    func testTheVectorsAreActuallyPresent() throws {
        XCTAssertGreaterThanOrEqual(try loadVectors().cases.count, 8,
                                    "les vecteurs manquent ou ont été tronqués")
    }

    /// Les deux cas qu'on ne verrait pas manquer.
    ///
    /// Le reste des vecteurs échoue bruyamment quand une phrase change. Ces
    /// deux-là échouent en silence s'ils disparaissent du fichier : la suite
    /// resterait verte en ayant cessé de couvrir l'observation la plus grave,
    /// et l'arrondi qui se trompe d'un point sans rien casser.
    func testTheVectorsStillCoverWhatMattersMost() throws {
        let names = try Set(loadVectors().cases.map(\.name))
        XCTAssertTrue(names.contains("chaine_rompue"),
                      "le cas de la chaîne rompue a disparu des vecteurs")
        XCTAssertTrue(names.contains("arrondi_sur_une_moitie"),
                      "le cas d'arrondi a disparu des vecteurs")
    }

    // MARK: Outillage

    private func loadVectors() throws -> VectorFile {
        let bundle = Bundle(for: type(of: self))
        let url = try XCTUnwrap(bundle.url(forResource: "notice_vectors", withExtension: "json"),
                               "notice_vectors.json n'est pas dans le bundle de test : "
                               + "vérifie qu'il est coché dans « Target Membership » pour la cible de tests")
        return try JSONDecoder().decode(VectorFile.self, from: Data(contentsOf: url))
    }

    private func makeJournal(from testCase: Case, origin: Date) throws -> Journal {
        let location = FileManager.default.temporaryDirectory
            .appendingPathComponent("vector-\(testCase.name)-\(UUID().uuidString).json")
        addTeardownBlock { try? FileManager.default.removeItem(at: location) }
        let journal = Journal(location: location)

        for item in testCase.entries {
            let created = origin.addingTimeInterval(Double(item.createdOffsetDays) * 86_400)
            let entry = try journal.add(
                title: item.title, action: item.action, predicted: item.predicted,
                probability: item.probability, tier: try XCTUnwrap(Tier(rawValue: item.tier)),
                costHours: item.costHours, horizonDays: item.horizonDays, now: created
            )
            if let happened = item.resolved {
                let at = created.addingTimeInterval(Double(item.horizonDays) * 86_400)
                try journal.resolve(entry.id, happened: happened, now: at)
            }
        }
        return journal
    }
}
