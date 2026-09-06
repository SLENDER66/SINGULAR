import Foundation

/// La hiérarchie de la constitution, dans son ordre.
///
/// Enregistrer à quel rang sert une décision est tout l'intérêt : c'est ainsi
/// qu'on découvre qu'on a passé un mois sur Patrimoine pendant que Revenus
/// restait vide.
///
/// Les valeurs brutes sont sans accent parce qu'elles sont écrites sur le
/// disque : un journal écrit aujourd'hui doit rester lisible dans dix ans quel
/// que soit ce qui a changé entre-temps. Ce qu'on montre à l'écran, lui, doit
/// être le mot juste — c'est `label`.
enum Tier: String, Codable, CaseIterable, Identifiable, Sendable {
    case stabilite = "STABILITE"
    case revenus = "REVENUS"
    case capacites = "CAPACITES"
    case opportunites = "OPPORTUNITES"
    case patrimoine = "PATRIMOINE"
    case liberte = "LIBERTE"

    var id: String { rawValue }

    /// 1 pour Stabilité, 6 pour Liberté.
    var rank: Int { (Tier.allCases.firstIndex(of: self) ?? 0) + 1 }

    var label: String {
        switch self {
        case .stabilite: return "Stabilité"
        case .revenus: return "Revenus"
        case .capacites: return "Capacités"
        case .opportunites: return "Opportunités"
        case .patrimoine: return "Patrimoine"
        case .liberte: return "Liberté"
        }
    }

    /// Les deux rangs sur lesquels la constitution ouvre.
    static let foundation: [Tier] = [.stabilite, .revenus]
}

enum EntryStatus: String, Codable, Sendable {
    case open = "OPEN"
    case happened = "HAPPENED"
    case didNotHappen = "DID_NOT_HAPPEN"
    case abandoned = "ABANDONED"
}
