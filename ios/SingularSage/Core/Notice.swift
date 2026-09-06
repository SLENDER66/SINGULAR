import Foundation

/// « Notice. » — ce que le Sage voit dans ton journal aujourd'hui.
///
/// Un rapport, pas une opinion. Chaque phrase produite ici est calculée à
/// partir d'entrées que tu as écrites toi-même : aucune n'est inventée, aucune
/// n'est adoucie, et rien n'a besoin d'un modèle de langage pour être vrai.
/// C'est volontaire. La facilité serait de faire commenter tes chiffres par un
/// LLM ; tu aurais alors un texte agréable dont tu ne pourrais vérifier aucune
/// affirmation. L'analyse en langage naturel viendra, et elle lira cette
/// structure plutôt que le journal directement.
///
/// Ce fichier est le portage du moteur de référence. Il doit rendre les mêmes
/// phrases, mot pour mot : `NoticeVectorTests` rejoue des journaux figés et
/// exige les textes que le moteur original produit. Une divergence ici ne
/// planterait pas — elle donnerait un conseil légèrement faux tous les matins,
/// sans rien dire. C'est pour ça que le test existe.

enum Severity: String, Codable, Comparable, Sendable {
    case critique = "CRITIQUE"
    case attention = "ATTENTION"
    case info = "INFO"

    var rank: Int {
        switch self {
        case .critique: return 0
        case .attention: return 1
        case .info: return 2
        }
    }

    static func < (lhs: Severity, rhs: Severity) -> Bool { lhs.rank < rhs.rank }
}

/// Ce qu'une observation appelle comme geste, quand elle en appelle un.
enum NoticeAction: Equatable, Sendable {
    case addDecision
    case resolve(String)
}

struct NoticeItem: Identifiable, Equatable, Sendable {
    let severity: Severity
    let title: String
    let detail: String
    var action: NoticeAction?
    var entryIDs: [String] = []

    var id: String { "\(severity.rawValue)|\(title)" }
}

struct Notice: Sendable {
    let headline: String
    let items: [NoticeItem]
    let report: Report
    let generatedAt: Date

    var severity: Severity { items.first?.severity ?? .info }
}

// MARK: - Les chiffres

/// Où vont tes heures, et ce que vaut ta confiance.
struct Report: Sendable {
    var decisions = 0
    var open = 0
    var overdue = 0
    var resolved = 0
    var hoursTotal = 0.0
    var hoursUnresolved = 0.0
    var hoursThatWorked = 0.0
    var meanProbability: Double?
    var hitRate: Double?
    var overconfidence: Double?
    var tiersWithDecisions: Set<Tier> = []
    var chainIntact = true

    static func build(entries: [Entry], at moment: Date, chainIntact: Bool) -> Report {
        var report = Report()
        report.chainIntact = chainIntact
        report.decisions = entries.count
        report.open = entries.filter(\.isOpen).count
        report.overdue = entries.filter { $0.isOverdue(at: moment) }.count

        let settled = entries.filter { $0.status == .happened || $0.status == .didNotHappen }
        report.resolved = settled.count
        report.hoursTotal = Numbers.round(entries.reduce(0) { $0 + $1.costHours }, places: 1)
        report.hoursUnresolved = Numbers.round(entries.filter(\.isOpen).reduce(0) { $0 + $1.costHours }, places: 1)
        report.hoursThatWorked = Numbers.round(
            entries.filter { $0.status == .happened }.reduce(0) { $0 + $1.costHours }, places: 1)
        report.tiersWithDecisions = Set(entries.map(\.tier))

        if !settled.isEmpty {
            // Les moyennes sont arrondies pour l'affichage, mais l'écart se
            // calcule sur les valeurs exactes : arrondir deux fois déplacerait
            // le seuil au-delà duquel le Sage se permet de te dire que tu te
            // surestimes.
            let meanProbability = settled.reduce(0) { $0 + $1.probability } / Double(settled.count)
            let hitRate = Double(settled.filter { $0.status == .happened }.count) / Double(settled.count)
            report.meanProbability = Numbers.round(meanProbability, places: 2)
            report.hitRate = Numbers.round(hitRate, places: 2)
            report.overconfidence = Numbers.round(meanProbability - hitRate, places: 2)
        }
        return report
    }
}

// MARK: - Les règles

enum NoticeEngine {

    /// Au-delà, un retard n'est plus un oubli : c'est une décision qu'on évite.
    static let lateDays = 7

    /// Écart de calibration à partir duquel il faut le dire. En deçà, le bruit
    /// d'échantillon explique l'écart aussi bien que la surconfiance.
    static let calibrationGap = 0.15

    /// Nombre de verdicts en dessous duquel une calibration ne veut rien dire.
    static let calibrationMinimum = 3

    static func build(entries: [Entry], at moment: Date, chainIntact: Bool) -> Notice {
        let report = Report.build(entries: entries, at: moment, chainIntact: chainIntact)
        let overdue = entries.filter { $0.isOverdue(at: moment) }.sorted { $0.dueAt < $1.dueAt }
        let overdueIDs = Set(overdue.map(\.id))
        let stillRunning = entries.filter { $0.isOpen && !overdueIDs.contains($0.id) }

        // L'ordre de construction est celui de la constitution : intégrité,
        // puis ce qui attend un verdict, puis les rangs fondateurs, puis ce que
        // vaut ta confiance.
        let candidates: [NoticeItem?] = [
            chainItem(report),
            overdueItem(overdue, at: moment),
            emptyItem(report),
            foundationItem(report),
            calibrationItem(report),
            unresolvedHoursItem(report),
            quietItem(stillRunning, at: moment),
        ]

        // Tri stable : à gravité égale, l'ordre ci-dessus est conservé.
        // `sorted(by:)` ne garantit pas la stabilité, donc l'indice départage.
        let items = candidates.compactMap { $0 }.enumerated()
            .sorted { ($0.element.severity.rank, $0.offset) < ($1.element.severity.rank, $1.offset) }
            .map(\.element)

        let headline = items.first.map { "Notice. \($0.title)." }
            ?? "Notice. Rien ne demande ton attention aujourd'hui."
        return Notice(headline: headline, items: items, report: report, generatedAt: moment)
    }

    // MARK: Observations

    private static func chainItem(_ report: Report) -> NoticeItem? {
        guard !report.chainIntact else { return nil }
        return NoticeItem(
            severity: .critique,
            title: "La chaîne du journal est rompue",
            detail: "Une prédiction a été modifiée ou supprimée après coup. Tant que c'est vrai, "
                + "aucune statistique de cette page ne vaut : elles portent sur un passé qui a été réécrit."
        )
    }

    private static func overdueItem(_ overdue: [Entry], at moment: Date) -> NoticeItem? {
        guard let first = overdue.first else { return nil }
        let worst = overdue.map { $0.overdueDays(at: moment) }.max() ?? 0
        let single = overdue.count == 1
        let subject = single ? "Elle attend" : "La plus ancienne attend"
        var detail = "\(plural(overdue.count, "décision a", "décisions ont")) dépassé "
            + "\(single ? "son" : "leur") horizon. "
        if worst == 0 {
            detail += "\(subject) un verdict depuis aujourd'hui."
        } else {
            detail += "\(subject) depuis \(worst) jour\(worst > 1 ? "s" : "")."
        }
        if worst > lateDays {
            detail += " Passé une semaine, un verdict qu'on ne rend pas n'est plus un oubli : "
                + "c'est le résultat qu'on préfère ne pas voir."
        }
        return NoticeItem(
            severity: worst > lateDays ? .critique : .attention,
            title: "À trancher aujourd'hui",
            detail: detail,
            action: .resolve(first.id),
            entryIDs: overdue.map(\.id)
        )
    }

    private static func emptyItem(_ report: Report) -> NoticeItem? {
        guard report.decisions == 0 else { return nil }
        return NoticeItem(
            severity: .attention,
            title: "Le journal est vide",
            detail: "Je ne peux rien t'apprendre sur toi tant que tu n'as rien prédit. "
                + "La première décision est la seule qui demande un effort ; ensuite c'est trente secondes.",
            action: .addDecision
        )
    }

    /// Les deux premiers rangs vides sont un défaut, même quand tout va bien.
    ///
    /// Sauf sur un journal vide, où ce serait dire deux fois la même chose.
    private static func foundationItem(_ report: Report) -> NoticeItem? {
        guard report.decisions > 0 else { return nil }
        let missing = Tier.foundation.filter { !report.tiersWithDecisions.contains($0) }
        guard !missing.isEmpty else { return nil }
        let names = missing.map(\.label).joined(separator: " et ")
        let single = missing.count == 1
        let detail = "Ta constitution ouvre sur \(Tier.foundation.map(\.label).joined(separator: " → ")). "
            + "\(single ? "Ce rang" : "Ces rangs") \(single ? "n’a" : "n’ont") reçu aucune décision, "
            + "alors que \(Numbers.compact(report.hoursTotal))h sont allées ailleurs."
        return NoticeItem(
            severity: .attention,
            title: "Aucune décision sur \(names)",
            detail: detail,
            action: .addDecision
        )
    }

    private static func calibrationItem(_ report: Report) -> NoticeItem? {
        guard let gap = report.overconfidence,
              let predicted = report.meanProbability,
              let happened = report.hitRate,
              report.resolved >= calibrationMinimum,
              abs(gap) >= calibrationGap else { return nil }
        if gap > 0 {
            return NoticeItem(
                severity: .attention,
                title: "Tu te surestimes de \(Numbers.signedPercent(gap))",
                detail: "Tu annonces \(Numbers.percent(predicted)) en moyenne ; il en arrive \(Numbers.percent(happened)). "
                    + "Sur \(report.resolved) verdicts, ce n'est plus de la malchance. "
                    + "Baisse tes probabilités d'autant, ou choisis des paris plus sûrs."
            )
        }
        return NoticeItem(
            severity: .info,
            title: "Tu te sous-estimes de \(Numbers.signedPercent(gap))",
            detail: "Tu annonces \(Numbers.percent(predicted)) ; il en arrive \(Numbers.percent(happened)). "
                + "Tu réussis plus souvent que tu ne l'oses : tes paris sont trop petits."
        )
    }

    /// De l'activité qui ne s'est jamais transformée en résultat.
    private static func unresolvedHoursItem(_ report: Report) -> NoticeItem? {
        let unresolved = report.hoursUnresolved
        let worked = report.hoursThatWorked
        guard unresolved != 0, unresolved > worked else { return nil }
        return NoticeItem(
            severity: worked == 0 ? .attention : .info,
            title: "\(Numbers.compact(unresolved))h engagées sans verdict",
            detail: "Contre \(Numbers.compact(worked))h qui ont produit ce que tu attendais. "
                + "C'est la définition que ta constitution donne de confondre activité et résultat."
        )
    }

    private static func quietItem(_ stillRunning: [Entry], at moment: Date) -> NoticeItem? {
        guard let nearest = stillRunning.min(by: { $0.dueAt < $1.dueAt }) else { return nil }
        let days = max(0, Int(floor(nearest.dueAt.timeIntervalSince(moment) / 86_400)))
        let when = days == 0 ? "aujourd'hui" : "dans \(days) jour\(days > 1 ? "s" : "")"
        return NoticeItem(
            severity: .info,
            title: plural(stillRunning.count, "décision ouverte", "décisions ouvertes"),
            detail: "La prochaine échéance tombe \(when) : "
                + "« \(nearest.predicted) », que tu donnes à \(Numbers.percent(nearest.probability)).",
            action: .resolve(nearest.id),
            entryIDs: [nearest.id]
        )
    }

    private static func plural(_ count: Int, _ singular: String, _ plural: String) -> String {
        "\(count) \(count == 1 ? singular : plural)"
    }
}

// MARK: - Mise en forme des nombres

/// Les mêmes conventions que le moteur de référence, sinon les phrases diffèrent.
enum Numbers {

    /// Arrondi au plus proche, moitiés vers le pair — la règle du moteur de
    /// référence, et celle que la norme IEEE applique par défaut.
    static func round(_ value: Double, places: Int) -> Double {
        let factor = pow(10.0, Double(places))
        return (value * factor).rounded(.toNearestOrEven) / factor
    }

    /// 60,0 → « 60 » ; 4,5 → « 4.5 ». Pas de zéro inutile derrière une heure.
    static func compact(_ value: Double) -> String {
        String(format: "%g", value)
    }

    /// 0,9 → « 90% ».
    static func percent(_ value: Double) -> String {
        String(format: "%.0f%%", value * 100)
    }

    /// +0,9 → « +90% ». Le signe fait partie de l'information.
    static func signedPercent(_ value: Double) -> String {
        String(format: "%+.0f%%", value * 100)
    }
}
