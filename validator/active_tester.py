import random

class StatementGenerator:
    def __init__(self):
        # Some random realish statements
        self.plausible_statements = [
            "The Eiffel Tower is located in Paris, France.",
            "Albert Einstein developed the theory of relativity.",
            "Bitcoin is a decentralized digital currency."
        ]
        # Some random nonsense/falsifiable statements
        self.nonsense_statements = [
            "Bloopdifs are universally harmonized in ancient texts.",
            "Zorple crystals can cure all diseases upon contact.",
            "The planet Nexaris orbits between Mars and Jupiter."
        ]

    def generate_statement(self) -> (str, bool):
        """
        Return a random statement and a bool indicating whether it's nonsense.
        The validator can use that to penalize or reward miners 
        who 'fake' corroborating nonsense statements.
        """
        # 50% chance of real vs nonsense
        if random.random() < 0.5:
            return random.choice(self.plausible_statements), False
        else:
            return random.choice(self.nonsense_statements), True
