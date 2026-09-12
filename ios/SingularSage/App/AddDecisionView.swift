import SwiftUI

/// Une décision, avant de la prendre.
///
/// Six champs et rien d'autre. Un outil qui demande plus de trente secondes est
/// un outil qu'on arrête d'utiliser, et un journal qu'on n'alimente pas
/// n'apprend rien.
@MainActor
struct AddDecisionView: View {
    @EnvironmentObject private var journal: Journal
    @Environment(\.dismiss) private var dismiss

    @State private var title = ""
    @State private var action = ""
    @State private var predicted = ""
    @State private var probability = 60.0
    @State private var tier: Tier = .revenus
    @State private var costHours = 4.0
    @State private var horizonDays = 14
    @State private var failure: String?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Postuler chez Anthropic", text: $title)
                } header: { Text("Décision, en une ligne") }

                Section {
                    TextField("candidature + projet joint", text: $action)
                } header: { Text("Ce que tu vas faire") }

                Section {
                    TextField("un entretien décroché", text: $predicted)
                } header: { Text("Le résultat observable que tu attends") }
                footer: {
                    Text("Il doit pouvoir être tranché par oui ou non. « le système sera plus clair » ne peut pas l'être.")
                }

                Section {
                    VStack(alignment: .leading) {
                        Text("\(Int(probability)) %")
                            .font(.title3.weight(.semibold))
                            .foregroundStyle(Theme.gold)
                        Slider(value: $probability, in: 5...95, step: 5)
                            .tint(Theme.gold)
                    }
                } header: { Text("Probabilité que ça arrive") }
                footer: {
                    Text("La certitude est refusée : elle ne peut pas avoir tort, donc elle n'apprend rien.")
                }

                Section {
                    Picker("Rang", selection: $tier) {
                        ForEach(Tier.allCases) { item in
                            Text("\(item.rank). \(item.label)").tag(item)
                        }
                    }
                } header: { Text("Rang de ta constitution") }
                footer: {
                    Text("Stabilité → Revenus → Capacités → Opportunités → Patrimoine → Liberté.")
                }

                Section {
                    Stepper("\(Numbers.compact(costHours)) heures", value: $costHours, in: 0...500, step: 0.5)
                    Stepper("Vérifier dans \(horizonDays) jour\(horizonDays > 1 ? "s" : "")",
                            value: $horizonDays, in: 1...365)
                } header: { Text("Ce que ça coûte, et quand on vérifie") }

                if let failure {
                    Section { Text(failure).foregroundStyle(Theme.colour(for: .critique)) }
                }
            }
            .navigationTitle("Nouvelle décision")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Annuler") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Enregistrer") { save() }.disabled(!isComplete)
                }
            }
        }
    }

    private var isComplete: Bool {
        ![title, action, predicted].contains { $0.trimmingCharacters(in: .whitespaces).isEmpty }
    }

    private func save() {
        do {
            try journal.add(title: title, action: action, predicted: predicted,
                            probability: probability / 100, tier: tier,
                            costHours: costHours, horizonDays: horizonDays)
            dismiss()
        } catch {
            failure = error.localizedDescription
        }
    }
}
