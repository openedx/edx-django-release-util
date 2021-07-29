from django.apps import AppConfig


class NonConcreteAppConfig(AppConfig):
    name = 'non_concrete_app'
    default = False
