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
    /// Les probabilités annoncées sur ce qui a été tranché, dans l'ordre.
    /// Une moyenne ne dit pas si un écart vient du hasard : voir
    /// `chanceDuHasard`.
    var resolvedProbabilities: [Double] = []
    /// Les mêmes verdicts, dans le même ordre, ramenés à « c'est arrivé ou non ».
    /// La moyenne ne dit pas *quand* il s'est trompé : voir
    /// `calibrationProgression`.
    var resolvedOutcomes: [Int] = []
    /// Les heures posées hors des rangs fondateurs — les seules que
    /// `foundationItem` a le droit d'appeler « ailleurs ».
    var hoursOutsideFoundation = 0.0
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
        report.resolvedProbabilities = settled.map(\.probability)
        report.resolvedOutcomes = settled.map { $0.status == .happened ? 1 : 0 }
        report.hoursOutsideFoundation = Numbers.round(
            entries.filter { !Tier.foundation.contains($0.tier) }.reduce(0) { $0 + $1.costHours },
            places: 1)

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

    /// Au-delà de quelle rareté un écart cesse de s'expliquer par le hasard.
    /// Une fois sur vingt — conventionnel, écrit plutôt que sous-entendu.
    static let calibrationHasard = 0.05

    /// Un demi-point : en deçà, la phrase dirait « tu te surestimes de +0% ».
    /// Plancher d'arrondi, pas plancher de jugement.
    static let calibrationArrondi = 0.005

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
        // « la plus en retard », pas « la plus ancienne » : ce sont deux
        // décisions différentes dès qu'un horizon long a été pris avant un
        // horizon court, et c'est du retard que ce nombre parle.
        let subject = single ? "Elle attend" : "La plus en retard attend"
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

    /// Un rang fondateur vide, dit quand c'en est un — et pas avant.
    ///
    /// Cette observation reprochait à Thomas, le lendemain de sa première
    /// décision, de n'avoir rien mis sur Stabilité. Il avait écrit une ligne,
    /// et une ligne ne peut pas occuper deux rangs : le constat portait sur de
    /// l'arithmétique, pas sur une conduite. Sa phrase était fausse en plus :
    /// « 4h sont allées ailleurs » comptait les heures posées sur Revenus, qui
    /// est un rang de la fondation.
    ///
    /// Deux conditions, une par défaut — autant de décisions que de rangs à
    /// couvrir, et des heures réellement passées hors fondation.
    private static func foundationItem(_ report: Report) -> NoticeItem? {
        let missing = Tier.foundation.filter { !report.tiersWithDecisions.contains($0) }
        guard !missing.isEmpty, report.decisions >= Tier.foundation.count else { return nil }
        let names = missing.map(\.label).joined(separator: " et ")
        let single = missing.count == 1
        let constat = "Ta constitution ouvre sur \(Tier.foundation.map(\.label).joined(separator: " → ")). "
            + "\(single ? "Ce rang" : "Ces rangs") \(single ? "n’a" : "n’ont") reçu aucune décision"
        if report.hoursOutsideFoundation == 0 {
            return NoticeItem(
                severity: .info,
                title: "Aucune décision sur \(names)",
                detail: "\(constat).",
                action: .addDecision
            )
        }
        return NoticeItem(
            severity: .attention,
            title: "Aucune décision sur \(names)",
            detail: constat + ", alors que \(Numbers.compact(report.hoursOutsideFoundation))h sont allées ailleurs.",
            action: .addDecision
        )
    }

    /// La chance qu'un écart au moins aussi grand sorte de probabilités justes.
    ///
    /// La distribution du nombre de réussites se construit en ajoutant les
    /// paris un par un : chaque pari déplace une part `p` du poids vers « une
    /// réussite de plus ». Exact même quand les probabilités diffèrent — une
    /// moyenne aurait approximé la réponse à la seule question pour laquelle
    /// ce journal existe.
    ///
    /// Mêmes opérations, dans le même ordre, que `chance_du_hasard` en Python :
    /// les vecteurs comparent les phrases produites, donc les nombres.
    /// La loi du nombre de réussites, exacte, quand chaque pari a sa probabilité.
    ///
    /// Deux questions s'en servent — « son écart vient-il du hasard ? » et
    /// « son écart est-il devenu petit ? » — et elles la calculaient chacune de
    /// leur côté avant que la seconde existe.
    static func distribution(_ probabilities: [Double]) -> [Double] {
        var distribution: [Double] = [1.0]
        for p in probabilities {
            var suivante = [Double](repeating: 0.0, count: distribution.count + 1)
            for (reussites, poids) in distribution.enumerated() {
                suivante[reussites] += poids * (1.0 - p)
                suivante[reussites + 1] += poids * p
            }
            distribution = suivante
        }
        return distribution
    }

    static func chanceDuHasard(_ probabilities: [Double], hits: Int) -> Double {
        guard !probabilities.isEmpty else { return 1.0 }
        let distribution = distribution(probabilities)
        let attendu = probabilities.reduce(0, +)
        let ecart = abs(Double(hits) - attendu)
        return distribution.enumerated()
            .filter { abs(Double($0.offset) - attendu) >= ecart - 1e-9 }
            .reduce(0.0) { $0 + $1.element }
    }

    /// « une fois sur 6 » — le chiffre qu'on lit, pas une probabilité à traduire.
    ///
    /// Le groupement des milliers est fait à la main, avec une espace fine
    /// insécable : un `NumberFormatter` dépend de la langue du téléphone, et
    /// deux appareils afficheraient deux phrases différentes.
    static func uneFoisSur(_ chance: Double) -> String {
        if chance <= 0 || 1.0 / chance > 1_000_000 {
            return "moins d'une fois sur un million"
        }
        let sur = max(2, Int((1.0 / chance).rounded()))
        var chiffres = Array(String(sur))
        var index = chiffres.count - 3
        while index > 0 {
            chiffres.insert("\u{202f}", at: index)
            index -= 3
        }
        return "une fois sur \(String(chiffres))"
    }

    /// Ce que valent ses probabilités — calculé une fois, pour tous ceux qui l'affichent.
    ///
    /// La vignette dorée du rapport gardait sa propre règle — « écart ≥ 15 % et
    /// 3 verdicts » — et s'allumait donc en alerte pendant que la phrase, juste
    /// en dessous, expliquait qu'il était trop tôt pour conclure. Deux réponses
    /// contradictoires à la même question, sur le même écran.
    struct CalibrationVerdict {
        let gap: Double
        let chance: Double
        let conclusive: Bool
    }

    static func calibrationVerdict(_ report: Report) -> CalibrationVerdict? {
        guard let gap = report.overconfidence, let hit = report.hitRate,
              report.resolved >= calibrationMinimum else { return nil }
        let hits = Int((hit * Double(report.resolved)).rounded())
        let hasard = chanceDuHasard(report.resolvedProbabilities, hits: hits)
        return CalibrationVerdict(
            gap: gap, chance: hasard,
            conclusive: hasard <= calibrationHasard && abs(gap) >= calibrationArrondi
        )
    }

    /// La chance de paraître aussi juste **en étant** biaisé d'au moins `borne`.
    ///
    /// `chanceDuHasard` répond à « son écart peut-il venir du hasard ? ». Elle
    /// ne répond pas à la question inverse, et c'est celle-là qui décide s'il
    /// faut se taire : « son écart est-il devenu petit ? ». Un écart non
    /// démontré n'est pas un écart démontré nul.
    ///
    /// On suppose donc qu'il se surestime d'au moins `borne` : chacune de ses
    /// prédictions à `p` n'arriverait qu'à `p - borne`. Sous cette hypothèse,
    /// quelle chance de réussir au moins autant qu'il a réussi ? Le symétrique
    /// tombe de la même façon pour la sous-estimation, et c'est le plus grand
    /// des deux qui est rendu.
    static func chanceDUnEcartMoindre(_ probabilities: [Double], hits: Int,
                                      borne: Double) -> Double {
        guard !probabilities.isEmpty, borne > 0 else { return 1.0 }
        let surestime = probabilities.map { min(1.0, max(0.0, $0 - borne)) }
        let sousestime = probabilities.map { min(1.0, max(0.0, $0 + borne)) }
        let haut = distribution(surestime).enumerated()
            .filter { $0.offset >= hits }.reduce(0.0) { $0 + $1.element }
        let bas = distribution(sousestime).enumerated()
            .filter { $0.offset <= hits }.reduce(0.0) { $0 + $1.element }
        return max(haut, bas)
    }

    /// Ce que vaut sa confiance sur une tranche de son journal.
    struct CalibrationPeriode {
        let verdicts: Int
        let gap: Double
        let chance: Double
        let conclusive: Bool
        let equivalence: Double
    }

    /// Les deux moitiés du journal, et si l'écart a été corrigé entre elles.
    struct CalibrationProgression {
        let debut: CalibrationPeriode
        let recent: CalibrationPeriode
        let corrige: Bool
    }

    private static func periode(_ probabilites: [Double],
                                _ resultats: [Int]) -> CalibrationPeriode {
        let verdicts = resultats.count
        // « Arrivé ou non », pas « combien » : un rapport d'une autre version ne
        // doit pas pouvoir gonfler le compte au-dessus du nombre de verdicts.
        let hits = resultats.filter { $0 != 0 }.count
        var gap = Numbers.round(probabilites.reduce(0, +) / Double(verdicts)
                                - Double(hits) / Double(verdicts), places: 2)
        if gap == 0 { gap = 0 }
        let hasard = chanceDuHasard(probabilites, hits: hits)
        return CalibrationPeriode(
            verdicts: verdicts, gap: gap, chance: hasard,
            conclusive: hasard <= calibrationHasard && abs(gap) >= calibrationArrondi,
            equivalence: chanceDUnEcartMoindre(probabilites, hits: hits, borne: calibrationGap)
        )
    }

    /// Son écart a une date, et le chiffre du jour ne la portait pas.
    ///
    /// `calibrationVerdict` mesure toute la vie du journal d'un seul bloc. Un
    /// biais corrigé il y a deux mois y pèse donc autant qu'hier, et la Notice
    /// continuait de dire « baisse tes probabilités d'autant » à quelqu'un qui
    /// les avait déjà baissées.
    ///
    /// Le journal est coupé en deux moitiés, dans l'ordre où les décisions ont
    /// été prises. `corrige` n'est vrai que si la première moitié montre un
    /// écart que le hasard n'explique pas *et* que la seconde démontre un écart
    /// inférieur à `calibrationGap`. Les deux, sinon rien : une moitié récente
    /// muette est une moitié sans preuve, pas une preuve d'amélioration.
    static func calibrationProgression(_ report: Report) -> CalibrationProgression? {
        let probabilites = report.resolvedProbabilities
        let resultats = report.resolvedOutcomes
        guard probabilites.count == resultats.count,
              resultats.count >= 2 * calibrationMinimum else { return nil }
        let coupe = resultats.count / 2
        let debut = periode(Array(probabilites[..<coupe]), Array(resultats[..<coupe]))
        let recent = periode(Array(probabilites[coupe...]), Array(resultats[coupe...]))
        return CalibrationProgression(
            debut: debut, recent: recent,
            corrige: debut.conclusive && recent.equivalence <= calibrationHasard
        )
    }

    private static func calibrationItem(_ report: Report) -> NoticeItem? {
        guard let verdict = calibrationVerdict(report),
              let predicted = report.meanProbability,
              let happened = report.hitRate,
              verdict.conclusive || abs(verdict.gap) >= calibrationGap else { return nil }

        let gap = verdict.gap
        let hasard = verdict.chance
        let constat = "Tu annonces \(Numbers.percent(predicted)) en moyenne ; "
            + "il en arrive \(Numbers.percent(happened))."

        if !verdict.conclusive {
            return NoticeItem(
                severity: .info,
                title: gap > 0 ? "Tu annonces plus que ce qui arrive"
                               : "Il arrive plus que ce que tu annonces",
                detail: constat + " Sur \(report.resolved) verdicts, un écart pareil sort "
                    + "du pur hasard \(uneFoisSur(hasard)) : c'est encore trop peu pour en "
                    + "conclure quoi que ce soit. Regarde-le sans le corriger."
            )
        }

        let progression = calibrationProgression(report)
        if let progression, progression.corrige {
            return NoticeItem(
                severity: .info,
                title: "Tu l'as déjà corrigé",
                detail: constat + " Mais cet écart est celui de tes "
                    + "\(progression.debut.verdicts) premières décisions : sur les "
                    + "\(progression.recent.verdicts) suivantes, il est démontré inférieur à "
                    + "\(Numbers.percent(calibrationGap)). Le chiffre du haut traîne ton "
                    + "passé. Ne corrige pas ce que tu as déjà corrigé."
            )
        }

        // « Baisse tes probabilités d'autant » ne se dit que si `d'autant` veut
        // dire quelque chose, c'est-à-dire tant qu'on n'a qu'un seul chiffre.
        let conseil: String
        if let progression {
            conseil = "Sur tes \(progression.recent.verdicts) plus récentes tranchées, "
                + "l'écart est de "
                + "\(Numbers.signedPercent(progression.recent.gap)) : c'est ce chiffre-là qui "
                + "dit où tu en es aujourd'hui, pas celui du haut. Corrige d'après lui."
        } else if gap > 0 {
            conseil = "Baisse tes probabilités d'autant, ou choisis des paris plus sûrs."
        } else {
            conseil = "Tu réussis plus souvent que tu ne l'oses, tes paris sont trop petits."
        }

        if gap > 0 {
            return NoticeItem(
                severity: .attention,
                title: "Tu te surestimes de \(Numbers.signedPercent(gap))",
                detail: constat + " Sur \(report.resolved) verdicts, ce n'est plus de la "
                    + "malchance : le hasard seul produirait cet écart \(uneFoisSur(hasard)). "
                    + conseil
            )
        }
        return NoticeItem(
            severity: .info,
            title: "Tu te sous-estimes de \(Numbers.signedPercent(gap))",
            detail: constat + " Sur \(report.resolved) verdicts, ce n'est plus de la "
                + "malchance : le hasard seul produirait cet écart \(uneFoisSur(hasard)). "
                + conseil
        )
    }

    /// De l'activité qui ne s'est jamais transformée en résultat.
    ///
    /// Le reproche attend qu'un verdict ait été rendu. Sans cette condition il
    /// tombait dès la première décision — « tu confonds activité et résultat »
    /// alors que l'échéance était dans treize jours et que rien n'aurait pu
    /// être tranché. « Contre 0h qui ont produit » compare à un ensemble vide
    /// tant que rien n'est tranché.
    private static func unresolvedHoursItem(_ report: Report) -> NoticeItem? {
        let unresolved = report.hoursUnresolved
        let worked = report.hoursThatWorked
        guard report.resolved > 0, unresolved != 0, unresolved > worked else { return nil }
        return NoticeItem(
            severity: worked == 0 ? .attention : .info,
            title: "\(Numbers.compact(unresolved))h engagées sans verdict",
            detail: "Contre \(Numbers.compact(worked))h qui ont produit ce que tu attendais. "
                + "C'est ce que ce rapport appelle confondre activité et résultat : ta "
                + "constitution nomme le piège dans sa mission, elle ne le mesure pas — la "
                + "mesure est celle-ci, et elle vaut ce que vaut ce rapport."
        )
    }

    private static func quietItem(_ stillRunning: [Entry], at moment: Date) -> NoticeItem? {
        guard let nearest = stillRunning.min(by: { $0.dueAt < $1.dueAt }) else { return nil }
        // En jours de calendrier, comme l'horizon : voir `Entry.dueDay`.
        let days = nearest.daysUntilDue(at: moment)
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
    /// référence.
    ///
    /// Passer par le texte plutôt que par `(value * 100).rounded()` n'est pas
    /// un détour. Multiplier d'abord déplace la valeur : 0,225 n'a pas
    /// d'écriture binaire exacte, et le produit par 100 tombe du mauvais côté
    /// de 22,5. La moitié qu'on croyait arrondir n'en est plus une, et le
    /// résultat bascule. Ce n'est pas théorique — quatre décisions annoncées à
    /// 5, 5, 5 et 75 % dont aucune n'arrive donnent exactement ce cas : le
    /// moteur de référence titre « Tu te surestimes de +23 % », et cette
    /// fonction, écrite avec la multiplication, répondait « +22 % ».
    ///
    /// Le formatage décimal arrondit la valeur binaire telle qu'elle est,
    /// sans étape intermédiaire — c'est ce que fait `round()` côté Python.
    /// `notice_vectors.json` contient le cas ci-dessus pour que la question
    /// ne se repose pas.
    static func round(_ value: Double, places: Int) -> Double {
        guard value.isFinite else { return value }
        return Double(String(format: "%.\(places)f", value)) ?? value
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
