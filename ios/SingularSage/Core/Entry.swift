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

    /// Le jour de l'échéance. Un horizon se donne en jours, il tombe un jour.
    ///
    /// `dueAt` vaut `createdAt + horizonDays`, donc il porte l'heure de
    /// l'écriture. Compté en instants, un horizon de 14 jours pris un soir à
    /// 20 h n'échoyait qu'à 20 h le quatorzième jour — et le rapport ouvert le
    /// matin ne réclamait rien ce jour-là. Le verdict était demandé le
    /// lendemain, systématiquement.
    ///
    /// Le calendrier est celui, fixe, qui a servi à écrire l'échéance : passer
    /// par le fuseau du téléphone ferait afficher deux jours différents pour
    /// la même décision sur deux appareils.
    var dueDay: Date { Calendar.singular.startOfDay(for: dueAt) }

    /// Depuis combien de jours cette décision attend un verdict.
    ///
    /// Des journées entières de calendrier, jamais négatives — le même compte
    /// que le moteur de référence. Compté en secondes, il manquait une
    /// demi-journée à chaque fois : le huitième jour s'annonçait comme le
    /// septième, et l'escalade en CRITIQUE arrivait un jour après ce que sa
    /// propre phrase promet.
    func overdueDays(at moment: Date) -> Int {
        let jours = Calendar.singular.dateComponents(
            [.day], from: dueDay, to: Calendar.singular.startOfDay(for: moment)).day ?? 0
        return max(0, jours)
    }

    /// Vrai dès que le jour de l'échéance a commencé.
    func isOverdue(at moment: Date) -> Bool {
        isOpen && Calendar.singular.startOfDay(for: moment) >= dueDay
    }

    /// Jours restants avant l'échéance, jamais négatif. Même unité que l'horizon.
    func daysUntilDue(at moment: Date) -> Int {
        let jours = Calendar.singular.dateComponents(
            [.day], from: Calendar.singular.startOfDay(for: moment), to: dueDay).day ?? 0
        return max(0, jours)
    }
}

extension Calendar {
    /// Un calendrier fixe, en UTC, pour calculer une échéance à l'écriture.
    static let singular: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0) ?? TimeZone(identifier: "UTC")!
        return calendar
    }()
}
