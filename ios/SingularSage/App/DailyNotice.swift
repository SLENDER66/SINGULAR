import Foundation
import UserNotifications

/// Le rappel du matin.
///
/// Une notification **locale** : elle est planifiée par l'app, sur le
/// téléphone, et ne traverse aucun serveur. C'est ce qui la rend possible sans
/// compte développeur payant — seules les notifications *distantes*, poussées
/// depuis un serveur, demandent ce compte. Comme cette app n'a pas de serveur,
/// elle n'en a pas besoin.
///
/// Le texte reste volontairement vague. Le contenu de ton journal ne doit pas
/// s'afficher sur un écran verrouillé qu'un autre peut lire par-dessus ton
/// épaule ; l'app te dit de venir, elle ne dit pas quoi.
enum DailyNotice {

    static let identifier = "singular.sage.daily"

    /// 8 h : avant que la journée ait commencé à décider à ta place.
    static let hour = 8
    static let minute = 0

    static func schedule() async {
        let center = UNUserNotificationCenter.current()
        guard let granted = try? await center.requestAuthorization(options: [.alert, .sound]),
              granted else { return }

        let content = UNMutableNotificationContent()
        content.title = "Notice."
        content.body = "Le Sage a regardé ton journal."
        content.sound = .default

        var when = DateComponents()
        when.hour = hour
        when.minute = minute

        let request = UNNotificationRequest(
            identifier: identifier,
            content: content,
            trigger: UNCalendarNotificationTrigger(dateMatching: when, repeats: true)
        )
        center.removePendingNotificationRequests(withIdentifiers: [identifier])
        try? await center.add(request)
    }
}
