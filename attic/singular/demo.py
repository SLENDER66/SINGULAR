from .agents import Commander
from .models import Action, Decision

def main():
    actions = [
        Action(id='A1', name='Action à fort levier', impact=8, urgency=7, leverage=9, effort=3, risk=2, reversibility=9, optionality=9),
        Action(id='A2', name='Action importante mais lourde', impact=9, urgency=6, leverage=5, effort=8, risk=4, reversibility=5, optionality=4),
        Action(id='A3', name='Petite optimisation', impact=4, urgency=5, leverage=4, effort=1, risk=1, reversibility=10, optionality=5),
    ]
    commander = Commander()
    result = commander.triage(actions)
    print('SINGULAR V1 CORE')
    print('NEXT BEST ACTION:', result['best_next_action']['name'])
    for row in result['ranked']:
        print(f"{row['action']['name']} => {row['score']}")

    d = Decision(id='D1', question='Faut-il engager une action à fort enjeu ?', options=['A','B'], recommendation='Tester une version réversible.', confidence=0.72, unknowns=['Coût réel'])
    assessed = commander.decide(d, consequence=9, reversibility=2)
    print('DECISION:', assessed['decision'].recommendation)
    print('HALT:', assessed['assessment'].halt)
    print('REASONS:', assessed['assessment'].reasons)

if __name__ == '__main__': main()
