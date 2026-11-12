from hypothesis import settings

settings.register_profile("fast", max_examples=25, stateful_step_count=10)
settings.register_profile("ci", max_examples=100, stateful_step_count=30)
settings.register_profile("extended", max_examples=500, stateful_step_count=60)
