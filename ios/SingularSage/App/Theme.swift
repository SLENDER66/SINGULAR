import SwiftUI

/// Sombre par défaut : cette app s'ouvre le matin et le soir, rarement en plein
/// jour, et elle doit tenir dans un pouce.
enum Theme {
    static let background = Color(red: 0.043, green: 0.051, blue: 0.063)
    static let raised = Color(red: 0.078, green: 0.094, blue: 0.114)
    static let line = Color(red: 0.137, green: 0.165, blue: 0.196)
    static let text = Color(red: 0.906, green: 0.925, blue: 0.949)
    static let muted = Color(red: 0.549, green: 0.592, blue: 0.647)
    static let gold = Color(red: 0.788, green: 0.635, blue: 0.153)

    static func colour(for severity: Severity) -> Color {
        switch severity {
        case .critique: return Color(red: 0.898, green: 0.282, blue: 0.302)
        case .attention: return Color(red: 0.851, green: 0.643, blue: 0.255)
        case .info: return Color(red: 0.310, green: 0.549, blue: 0.788)
        }
    }
}

extension View {
    func cardBackground() -> some View {
        background(Theme.raised)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(Theme.line, lineWidth: 1)
            )
    }
}
