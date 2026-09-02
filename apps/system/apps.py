from django.apps import AppConfig


class SystemConfig(AppConfig):
    name = 'apps.system'
    label = 'system'

    def ready(self):
        """Install runtime compatibility helpers for user access checks."""
        # Provide a runtime-only `profile` compatibility property on User so
        # templates and code referencing `user.profile` work without touching
        # the archived profile table.
        from django.contrib.auth.models import User

        def _profile(self):
            # Persist a small compatibility dict on the user instance for the
            # duration of the process (tests/requests).
            if '_compat_profile' not in self.__dict__:
                dept = 'mayor'
                if getattr(self, 'is_superuser', False):
                    dept = 'admin'
                else:
                    try:
                        from apps.system.models import UserFlag
                        flag = UserFlag.objects.filter(user=self).first()
                        if flag and getattr(flag, 'department', None):
                            dept = flag.department
                        elif getattr(self, 'is_staff', False):
                            dept = 'engineer'
                    except Exception:
                        if getattr(self, 'is_staff', False):
                            dept = 'engineer'
                self.__dict__['_compat_profile'] = {'department': dept}

            class _P:
                def __init__(self, user):
                    object.__setattr__(self, '_user', user)

                def __getattr__(self, item):
                    # Check in-memory compat profile first
                    if item in self._user._compat_profile:
                        return self._user._compat_profile.get(item)
                    return None

                def __setattr__(self, key, value):
                    self._user._compat_profile[key] = value

                def __repr__(self):
                    return f"CompatProfile({self._user._compat_profile})"

            return _P(self)

        # Replace any existing `profile` attribute on User with a runtime-only
        # compatibility property so code and templates do not attempt to access
        # the archived profile table at runtime.
        setattr(User, 'profile', property(_profile))
