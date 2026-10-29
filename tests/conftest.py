import os

from hypothesis import settings

settings.register_profile('dev', max_examples=25)
settings.register_profile('ci', max_examples=200, deadline=None)
settings.register_profile('big', max_examples=5000, deadline=None)
settings.load_profile(os.getenv('HYPOTHESIS_PROFILE', 'dev'))
