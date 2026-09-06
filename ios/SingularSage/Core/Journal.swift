import Foundation
import CryptoKit

/// Le journal : ce que tu as prédit, ce qui est arrivé, chaîné pour qu'on ne
/// puisse pas le réécrire.
///
/// Le stockage est un fichier JSON écrit d'un bloc, pas une base SQLite. Ce
/// n'est pas de la paresse : il y a un seul écrivain — toi, sur ce téléphone —
/// et quelques centaines d'entrées sur une vie. SQLite n'apporterait ici que du
/// pont C à faire vivre, pendant que le fichier JSON se lit à l'œil nu, se
/// sauvegarde en le copiant et survit à toutes les migrations du système.
///
/// L'écriture est atomique : le fichier est complet ou il est l'ancien, jamais
/// à moitié écrit. Un journal tronqué par une batterie vide serait pire qu'un
/// journal absent, parce qu'il aurait l'air d'être là.
@MainActor
final class Journal: ObservableObject {

    @Published private(set) var entries: [Entry] = []

    /// Non nul quand le fichier existe mais n'a pas pu être lu. Tant que c'est
    /// le cas, aucune écriture n'est acceptée : le journal en mémoire ne
    /// représente pas ce qui est sur le disque.
    @Published private(set) var loadFailure: String?

    private let location: URL
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    enum JournalError: LocalizedError, Equatable {
        case invalidProbability
        case invalidHorizon
        case missingField(String)
        case unknownEntry(String)
        case alreadyResolved(String)
        case unreadable(String)

        var errorDescription: String? {
            switch self {
            case .invalidProbability:
                return "La probabilité doit être strictement entre 0 et 1 : une certitude ne peut pas avoir tort, donc elle n'apprend rien."
            case .invalidHorizon:
                return "Il faut au moins un jour d'horizon pour pouvoir vérifier."
            case .missingField(let name):
                return "« \(name) » est obligatoire."
            case .unknownEntry(let id):
                return "\(id) n'existe pas."
            case .alreadyResolved(let id):
                return "\(id) a déjà été tranchée ; l'histoire n'est pas modifiable."
            case .unreadable(let reason):
                return "Le journal existe mais n'a pas pu être lu (\(reason)). "
                    + "Rien ne sera écrit tant que ce n'est pas réglé : écrire maintenant "
                    + "remplacerait ton historique par un journal vide."
            }
        }
    }

    init(location: URL? = nil) {
        self.location = location ?? Journal.defaultLocation()
        encoder.dateEncodingStrategy = .iso8601
        decoder.dateDecodingStrategy = .iso8601
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        load()
    }

    static func defaultLocation() -> URL {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        return documents.appendingPathComponent("journal.json")
    }

    // MARK: - Écriture

    /// Enregistrer une décision **avant** de la prendre.
    @discardableResult
    func add(title: String, action: String, predicted: String, probability: Double,
             tier: Tier, costHours: Double, horizonDays: Int, now: Date = Date()) throws -> Entry {
        try requireReadableStore()
        let title = title.trimmingCharacters(in: .whitespacesAndNewlines)
        let action = action.trimmingCharacters(in: .whitespacesAndNewlines)
        let predicted = predicted.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty else { throw JournalError.missingField("décision") }
        guard !action.isEmpty else { throw JournalError.missingField("ce que tu vas faire") }
        guard !predicted.isEmpty else { throw JournalError.missingField("résultat attendu") }
        guard probability > 0, probability < 1, probability.isFinite else { throw JournalError.invalidProbability }
        guard horizonDays >= 1 else { throw JournalError.invalidHorizon }
        let costHours = costHours.isFinite ? max(costHours, 0) : 0

        let previous = entries.last?.fingerprint ?? ""
        let identifier = "DEC-" + UUID().uuidString.replacingOccurrences(of: "-", with: "").prefix(8).lowercased()
        let due = Calendar.singular.date(byAdding: .day, value: horizonDays, to: now) ?? now

        let material = Journal.material(
            id: String(identifier), title: title, action: action, predicted: predicted,
            probability: probability, tier: tier, costHours: costHours,
            horizonDays: horizonDays, createdAt: now, previous: previous
        )

        let entry = Entry(
            id: String(identifier), title: title, action: action, predicted: predicted,
            probability: probability, tier: tier, costHours: costHours, horizonDays: horizonDays,
            createdAt: now, dueAt: due, status: .open, resolvedAt: nil, lesson: nil,
            brierScore: nil, previousFingerprint: previous, fingerprint: Journal.digest(material)
        )
        entries.append(entry)
        save()
        return entry
    }

    /// Enregistrer ce qui s'est passé. Note la prédiction, ne la réécrit pas.
    @discardableResult
    func resolve(_ id: String, happened: Bool, lesson: String = "", now: Date = Date()) throws -> Entry {
        try requireReadableStore()
        guard let index = entries.firstIndex(where: { $0.id == id }) else {
            throw JournalError.unknownEntry(id)
        }
        guard entries[index].status == .open else { throw JournalError.alreadyResolved(id) }
        let outcome = happened ? 1.0 : 0.0
        entries[index].status = happened ? .happened : .didNotHappen
        entries[index].resolvedAt = now
        entries[index].lesson = lesson.isEmpty ? nil : lesson
        // Score de Brier : l'écart au carré entre ce que tu annonçais et ce qui
        // est arrivé. 0 = parfait, 0,25 = pile ou face.
        entries[index].brierScore = pow(entries[index].probability - outcome, 2)
        save()
        return entries[index]
    }

    /// Arrêter une décision, en le disant. Abandonner est un résultat.
    @discardableResult
    func abandon(_ id: String, reason: String, now: Date = Date()) throws -> Entry {
        try requireReadableStore()
        guard let index = entries.firstIndex(where: { $0.id == id }) else {
            throw JournalError.unknownEntry(id)
        }
        guard entries[index].status == .open else { throw JournalError.alreadyResolved(id) }
        entries[index].status = .abandoned
        entries[index].resolvedAt = now
        entries[index].lesson = reason.trimmingCharacters(in: .whitespacesAndNewlines)
        save()
        return entries[index]
    }

    // MARK: - Lecture

    func open() -> [Entry] { entries.filter(\.isOpen) }

    func due(at moment: Date = Date()) -> [Entry] {
        entries.filter { $0.isOverdue(at: moment) }.sorted { $0.dueAt < $1.dueAt }
    }

    /// La chaîne a-t-elle été rompue depuis que les entrées ont été écrites ?
    func verify() -> Bool {
        var previous = ""
        for entry in entries {
            let material = Journal.material(
                id: entry.id, title: entry.title, action: entry.action, predicted: entry.predicted,
                probability: entry.probability, tier: entry.tier, costHours: entry.costHours,
                horizonDays: entry.horizonDays, createdAt: entry.createdAt, previous: previous
            )
            if entry.previousFingerprint != previous || Journal.digest(material) != entry.fingerprint {
                return false
            }
            previous = entry.fingerprint
        }
        return true
    }

    // MARK: - Empreinte

    /// Ce que couvre l'empreinte, écrit une fois et lu par `add` et `verify`.
    ///
    /// Les nombres sont convertis en entiers avant d'être joints. Écrire un
    /// `Double` en texte dépend du formateur, de la version, parfois de la
    /// langue du téléphone : une empreinte calculée à l'écriture et recalculée
    /// à la lecture doit tomber sur la même chaîne d'octets, toujours. Une
    /// probabilité au dix-millième et un coût à la minute sont largement plus
    /// fins que ce qu'on sait estimer.
    private static func material(id: String, title: String, action: String, predicted: String,
                                 probability: Double, tier: Tier, costHours: Double,
                                 horizonDays: Int, createdAt: Date, previous: String) -> String {
        let separator = "\u{1f}"
        let fields: [String] = [
            previous, id, title, action, predicted,
            String(Int((probability * 10_000).rounded())),
            tier.rawValue,
            String(Int((costHours * 100).rounded())),
            String(horizonDays),
            ISO8601DateFormatter.singular.string(from: createdAt),
        ]
        return fields.joined(separator: separator)
    }

    private static func digest(_ material: String) -> String {
        SHA256.hash(data: Data(material.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    // MARK: - Disque

    /// Charger le journal, en distinguant « pas encore de fichier » de
    /// « fichier illisible ».
    ///
    /// C'était `(try? decoder.decode(...)) ?? []`, et cette ligne perdait des
    /// années de journal sans rien dire. Un fichier corrompu, tronqué par une
    /// batterie vide, ou écrit par une version future du format donnait un
    /// journal vide ; l'app affichait « Le journal est vide » ; la première
    /// décision enregistrée repartait sur une chaîne neuve et **écrasait le
    /// fichier**. Une lecture qui échoue en rendant « rien » est indiscernable
    /// d'une lecture qui réussit sur un journal neuf, et c'est exactement la
    /// condition dans laquelle on accepte d'écrire par-dessus.
    ///
    /// Un fichier absent est légitime : c'est le premier lancement. Un fichier
    /// présent et illisible arrête les écritures jusqu'à ce que quelqu'un
    /// regarde.
    private func load() {
        guard FileManager.default.fileExists(atPath: location.path) else { return }
        do {
            entries = try decoder.decode([Entry].self, from: Data(contentsOf: location))
        } catch {
            loadFailure = error.localizedDescription
            entries = []
        }
    }

    /// Écrire, sauf si ce qu'on a en mémoire ne vient pas du fichier.
    private func save() {
        guard loadFailure == nil, let data = try? encoder.encode(entries) else { return }
        // `.atomic` : le fichier est l'ancien ou le nouveau, jamais un mélange
        // des deux. Un journal tronqué aurait l'air d'être là.
        try? data.write(to: location, options: .atomic)
    }

    /// Vérifier avant toute écriture qu'on n'est pas en train de repartir de zéro.
    private func requireReadableStore() throws {
        if let failure = loadFailure {
            throw JournalError.unreadable(failure)
        }
    }
}

extension ISO8601DateFormatter {
    /// Un seul formateur, en UTC : deux formats différents dans le même fichier
    /// rendraient les dates incomparables.
    static let singular: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        return formatter
    }()
}
