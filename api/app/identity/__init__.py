"""Dev identity (mock).

``IdentityProvider`` is the seam a real OIDC implementation drops into later. The
only implementation today is :class:`~app.identity.mock.MockIdentityProvider`,
which signs fake JWT-like claims with a local HS256 secret. No passwords, no
OIDC, no user store beyond the seeded fake users.
"""

from app.identity.base import Claims, IdentityError, IdentityProvider
from app.identity.mock import MockIdentityProvider

__all__ = ["Claims", "IdentityError", "IdentityProvider", "MockIdentityProvider"]
