"""_example — throwaway demonstration slice proving the persistence seam.

NOT a business module: no router, no domain rules. It exists so the first real
module can copy the pattern:

    ports/           the repository Protocol + DTOs (no engine knowledge)
    infrastructure/  asyncpg adapter + in-memory fake (the ONLY engine-aware code)

Delete this package once the first real module lands, or keep it as reference.
"""
