import SwiftUI

@main
struct SingularSageApp: App {
    @StateObject private var journal = Journal()

    var body: some Scene {
        WindowGroup {
            BriefView()
                .environmentObject(journal)
                .preferredColorScheme(.dark)
                .task { await DailyNotice.schedule() }
        }
    }
}
