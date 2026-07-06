"""Feature modules land here, one package per module:

    modules/<name>/domain          # entities, value objects, domain services
    modules/<name>/application    # use cases, ports (repository Protocols)
    modules/<name>/api            # routers + schemas (delivery only)
    modules/<name>/infrastructure # adapters: the ONLY place the engine is known

Empty in M0 by design; excluded from the import smoke test.
"""
