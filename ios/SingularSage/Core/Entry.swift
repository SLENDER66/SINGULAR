import Foundation

/// Une décision : ce que tu attendais, et ce qui est arrivé.
///
/// `previousFingerprint` et `fingerprint` chaînent les entrées entre elles.
/// Une prédiction modifiée après coup casse la chaîne et le Sage le dit — un
/// journal qu'on peut retoucher n'apprend rien à personne.
struct Entry: Codable, Identifiable, Equatable, Sendable {
    let id: String
    var title: String
    var action: String
    var predicted: String
    var probability: Double
    var tier: Tier
    var costHours: Double
    var horizonDays: Int
    var createdAt: Date
    var dueAt: Date
    var status: EntryStatus
    var resolvedAt: Date?
    var lesson: String?
    var brierScore: Double?
    var previousFingerprint: String
    var fingerprint: String

    var isOpen: Bool { status == .open }

    /// Depuis combien de jours cette décision attend un verdict.
    ///
    /// Des journées entières écoulées, arrondies vers le bas, et jamais
    /// négatives — le même compte que le moteur de référence. Passer par un
    /// calendrier ferait dépendre le résultat du fuseau du téléphone : deux
    /// appareils afficheraient deux retards différents pour la même décision.
    func overdueDays(at moment: Date) -> Int {
        max(0, Int(floor(moment.timeIntervalSince(dueAt) / 86_400)))
    }

    func isOverdue(at moment: Date) -> Bool { isOpen && dueAt <= moment }
}

extension Calendar {
    /// Un calendrier fixe, en UTC, pour calculer une échéance à l'écriture.
    static let singular: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0) ?? TimeZone(identifier: "UTC")!
        return calendar
    }()
}
