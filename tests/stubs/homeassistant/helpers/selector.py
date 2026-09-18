class EntitySelectorConfig(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

class EntitySelector:
    def __init__(self, config=None):
        self.config = config
