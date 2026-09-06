import SwiftUI

/// Ce qui s'est réellement passé.
///
/// Deux boutons, parce que c'est une question à deux réponses. Abandonner en
/// est une troisième, honnête : laisser une décision ouverte pour toujours ne
/// l'est pas.
struct ResolveSheet: View {
    let entry: Entry

    @EnvironmentObject private var journal: Journal
    @Environment(\.dismiss) private var dismiss
    @State private var lesson = ""
    @State private var abandoning = false
    @State private var failure: String?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("« \(entry.predicted) »")
                        .font(.body)
                        .foregroundStyle(Theme.text)
                    Text("Tu disais \(Numbers.percent(entry.probability)) · \(entry.tier.label) · \(Numbers.compact(entry.costHours))h")
                        .font(.footnote)
                        .foregroundStyle(Theme.muted)
                }

                Section {
                    TextField("facultatif", text: $lesson, axis: .vertical)
                } header: { Text("Ce que tu en retiens") }

                Section {
                    Button { resolve(happened: true) } label: {
                        Label("C'est arrivé", systemImage: "checkmark.circle")
                    }
                    Button { resolve(happened: false) } label: {
                        Label("Ce n'est pas arrivé", systemImage: "xmark.circle")
                    }
                    .foregroundStyle(Theme.colour(for: .critique))
                }

                Section {
                    Button("Abandonner cette décision") { abandoning = true }
                        .foregroundStyle(Theme.muted)
                } footer: {
                    Text("Abandonner est un résultat. Laisser une décision ouverte pour toujours n'en est pas un.")
                }

                if let failure {
                    Section { Text(failure).foregroundStyle(Theme.colour(for: .critique)) }
                }
            }
            .navigationTitle("Qu'est-ce qui s'est passé ?")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Annuler") { dismiss() }
                }
            }
            .alert("Abandonner ?", isPresented: $abandoning) {
                Button("Annuler", role: .cancel) {}
                Button("Abandonner", role: .destructive) { abandon() }
            } message: {
                Text("La décision sera close sans verdict, avec ce que tu as écrit comme raison.")
            }
        }
    }

    private func resolve(happened: Bool) {
        do {
            try journal.resolve(entry.id, happened: happened, lesson: lesson)
            dismiss()
        } catch {
            failure = error.localizedDescription
        }
    }

    private func abandon() {
        do {
            try journal.abandon(entry.id, reason: lesson.isEmpty ? "abandonnée" : lesson)
            dismiss()
        } catch {
            failure = error.localizedDescription
        }
    }
}
