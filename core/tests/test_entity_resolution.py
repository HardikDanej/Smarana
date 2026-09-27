from memory_os.entity_resolution import EntityResolver


def test_case_and_punctuation_variants_resolve_to_the_same_entity():
    resolver = EntityResolver()
    canonical = resolver.resolve("OpenAI")
    assert resolver.resolve("open ai") == canonical
    assert resolver.resolve("OPENAI") == canonical


def test_corporate_suffix_is_normalized_away():
    resolver = EntityResolver()
    canonical = resolver.resolve("OpenAI")
    assert resolver.resolve("OpenAI Inc.") == canonical


def test_first_seen_surface_form_becomes_canonical():
    resolver = EntityResolver()
    first = resolver.resolve("Project Alpha")
    assert first == "Project Alpha"
    assert resolver.resolve("project alpha") == "Project Alpha"


def test_unrelated_entities_stay_distinct():
    resolver = EntityResolver()
    resolver.resolve("Project Alpha")
    assert resolver.resolve("Project Beta") == "Project Beta"


def test_explicit_alias_overrides_automatic_matching():
    resolver = EntityResolver()
    resolver.resolve("Project Alpha")
    resolver.register_alias("Alpha", "Project Alpha")
    assert resolver.resolve("Alpha") == "Project Alpha"
