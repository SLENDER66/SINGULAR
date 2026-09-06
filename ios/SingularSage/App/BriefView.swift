import SwiftUI
import UIKit

/// L'écran qu'on ouvre le matin : ce que le Sage a vu, et ce qu'il attend de toi.
@MainActor
struct BriefView: View {
    @EnvironmentObject private var journal: Journal
    @State private var addingDecision = false
    @State private var resolving: Entry?
    @State private var now = Date()

    private var notice: Notice {
        NoticeEngine.build(entries: journal.entries, at: now, chainIntact: journal.verify())
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 26) {
                    header
                    storageFailure
                    observations
                    figures
                    openDecisions
                }
                .padding(20)
                .padding(.bottom, 80)
            }
            .background(Theme.background.ignoresSafeArea())
            .scrollIndicators(.hidden)
            .overlay(alignment: .bottomTrailing) { addButton }
            .toolbar(.hidden, for: .navigationBar)
        }
        // Rouvrir l'app doit montrer aujourd'hui, pas la dernière fois qu'on l'a
        // regardée : un retard affiché à J-1 est un retard qu'on ne traite pas.
        .onReceive(NotificationCenter.default.publisher(
            for: UIApplication.willEnterForegroundNotification)) { _ in now = Date() }
        .sheet(isPresented: $addingDecision) { AddDecisionView() }
        .sheet(item: $resolving) { entry in ResolveSheet(entry: entry) }
    }

    // MARK: Morceaux

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("SINGULAR")
                .font(.system(size: 11, weight: .semibold))
                .tracking(2)
                .foregroundStyle(Theme.gold)
            Text(notice.headline)
                .font(.system(size: 27, weight: .semibold))
                .foregroundStyle(Theme.text)
                .fixedSize(horizontal: false, vertical: true)
            Text(now.formatted(.dateTime.weekday(.wide).day().month(.wide)))
                .font(.footnote)
                .foregroundStyle(Theme.muted)
        }
    }

    /// Un journal illisible ne doit jamais ressembler à un journal vide.
    ///
    /// C'est la différence entre « tu n'as rien écrit » et « ton historique est
    /// là mais je n'arrive pas à le lire » — et la deuxième interdit d'écrire,
    /// sans quoi la première décision enregistrée l'écraserait.
    @ViewBuilder
    private var storageFailure: some View {
        if let failure = journal.loadFailure {
            VStack(alignment: .leading, spacing: 6) {
                Text("Ton journal n'a pas pu être lu")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(Theme.text)
                Text("Il est là, mais illisible : \(failure)\n\nAucune écriture n'est acceptée tant que "
                     + "ce n'est pas réglé — enregistrer une décision maintenant remplacerait "
                     + "ton historique par un journal vide.")
                    .font(.footnote)
                    .foregroundStyle(Theme.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(14)
            .background(Theme.colour(for: .critique).opacity(0.12))
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(Theme.colour(for: .critique), lineWidth: 1)
            )
        }
    }

    private var observations: some View {
        VStack(spacing: 12) {
            ForEach(notice.items) { item in
                observation(item)
            }
        }
    }

    private func observation(_ item: NoticeItem) -> some View {
        HStack(alignment: .top, spacing: 0) {
            Rectangle()
                .fill(Theme.colour(for: item.severity))
                .frame(width: 3)
            VStack(alignment: .leading, spacing: 6) {
                Text(item.title)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(Theme.text)
                Text(item.detail)
                    .font(.footnote)
                    .foregroundStyle(Theme.muted)
                    .fixedSize(horizontal: false, vertical: true)
                if let action = item.action {
                    button(for: action)
                        .padding(.top, 6)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(14)
        }
        .cardBackground()
    }

    @ViewBuilder
    private func button(for action: NoticeAction) -> some View {
        switch action {
        case .addDecision:
            pill("Enregistrer une décision") { addingDecision = true }
        case .resolve(let id):
            if let entry = journal.entries.first(where: { $0.id == id }) {
                pill("Trancher maintenant") { resolving = entry }
            }
        }
    }

    private func pill(_ label: String, action: @escaping () -> Void) -> some View {
        Button(label, action: action)
            .font(.footnote)
            .foregroundStyle(Theme.text)
            .padding(.horizontal, 15)
            .padding(.vertical, 7)
            .overlay(Capsule().stroke(Theme.line, lineWidth: 1))
    }

    @ViewBuilder
    private var figures: some View {
        let report = notice.report
        if report.decisions > 0 {
            VStack(alignment: .leading, spacing: 12) {
                sectionTitle("Où vont tes heures")
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                    figure(Numbers.compact(report.hoursTotal) + "h", "engagées en tout")
                    figure(Numbers.compact(report.hoursThatWorked) + "h", "ont produit le résultat attendu",
                           warn: report.hoursThatWorked == 0 && report.resolved > 0)
                    figure(Numbers.compact(report.hoursUnresolved) + "h", "encore sans verdict",
                           warn: report.hoursUnresolved > report.hoursThatWorked)
                    figure("\(report.overdue)", "à trancher", warn: report.overdue > 0)
                    if let gap = report.overconfidence, report.resolved >= NoticeEngine.calibrationMinimum,
                       let hit = report.hitRate, let mean = report.meanProbability {
                        figure(Numbers.signedPercent(gap),
                               gap > 0 ? "de surconfiance" : "de sous-confiance",
                               warn: abs(gap) >= NoticeEngine.calibrationGap)
                        figure(Numbers.percent(hit), "arrivent, sur \(Numbers.percent(mean)) annoncés")
                    }
                }
            }
        }
    }

    private func figure(_ value: String, _ label: String, warn: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(value)
                .font(.system(size: 24, weight: .semibold))
                .foregroundStyle(warn ? Theme.colour(for: .attention) : Theme.text)
            Text(label)
                .font(.caption2)
                .foregroundStyle(Theme.muted)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .cardBackground()
    }

    @ViewBuilder
    private var openDecisions: some View {
        let open = journal.open().sorted { $0.dueAt < $1.dueAt }
        if !open.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                sectionTitle("Décisions ouvertes")
                ForEach(open) { entry in
                    Button { resolving = entry } label: { row(entry) }
                        .buttonStyle(.plain)
                }
            }
        }
    }

    private func row(_ entry: Entry) -> some View {
        let late = entry.overdueDays(at: now)
        return HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text(entry.title)
                .font(.subheadline)
                .foregroundStyle(Theme.text)
                .frame(maxWidth: .infinity, alignment: .leading)
            Text(late > 0
                 ? "+\(late)j · \(Numbers.percent(entry.probability))"
                 : "\(Numbers.percent(entry.probability)) · \(entry.tier.label)")
                .font(.caption2)
                .foregroundStyle(late > 0 ? Theme.colour(for: .critique) : Theme.muted)
        }
        .padding(.horizontal, 15)
        .padding(.vertical, 13)
        .cardBackground()
    }

    private func sectionTitle(_ text: String) -> some View {
        Text(text.uppercased())
            .font(.system(size: 12, weight: .semibold))
            .tracking(1.5)
            .foregroundStyle(Theme.muted)
    }

    private var addButton: some View {
        Button { addingDecision = true } label: {
            Image(systemName: "plus")
                .font(.system(size: 26, weight: .medium))
                .foregroundStyle(Theme.background)
                .frame(width: 60, height: 60)
                .background(Theme.gold, in: Circle())
                .shadow(color: .black.opacity(0.5), radius: 12, y: 6)
        }
        .padding(20)
        .accessibilityLabel("Enregistrer une décision")
    }
}
