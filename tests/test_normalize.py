from scraper.normalize import _derive_category


def test_category_aliases_fold_into_art():
    for name in [
        "Calligraphy - Field Trip: PSU Library Special Collections",
        "Ceramics - Youth: Wheel Throwing",
        "Fiber Arts - Weaving - On Loom: Beginning",
        "Mixed Media - Encaustic Painting",
        "Sewing - Beginner",
    ]:
        assert _derive_category(name) == "Art"


def test_category_aliases_fold_into_dance():
    for name in ["Ballet - Basics", "Creative Dance - Preschool"]:
        assert _derive_category(name) == "Dance"


def test_pool_name_prefixes_fold_into_aquatics():
    """Some swim lesson listings use the pool's name instead of a category."""
    for name in [
        "Creston - Goldfish",
        "EPCC - Sea Lion",
        "Grant - Seal",
        "Ida B. Wells - Angelfish",
        "Peninsula - Polar Bear",
    ]:
        assert _derive_category(name) == "Aquatics"


def test_removed_categories_become_uncategorized():
    for name in [
        "Adaptive - Bocce Ball",
        "Summer Swim Team - Creston",
        "TeenForce - Boxing: Personal Power",
        "Continuing Education - Book Club",
        "Conversations on Aging - Downsizing - Friendly House",
        "Hike for Health II - Bachelor Mountain",
        "Hike for Health III - The Ponds",
        "Book Arts & Woodworking - Bookbinding",
        "Hiking & Walking - Forest Park",
        "Meet Us There AR - Group Hike",
        "Van Trip - Coast Excursion",
        "Virtual Fitness - Chair Yoga",
        "Virtual Programming - Trivia Night",
        "Camp - Summertime Thrills: Week of 8/03 (Grades 1-3)",
    ]:
        assert _derive_category(name) is None


def test_unrelated_categories_pass_through_unchanged():
    assert _derive_category("Art - Extravaganza : Mixed Media") == "Art"
    assert _derive_category("Basketball - For Starters") == "Basketball"
    # Previously removed for being 11+/13+/14+/16+ only, then restored per
    # user request to keep under-10 activities like Pickleball available.
    assert _derive_category("Tennis - Junior Development") == "Tennis"
    assert _derive_category("Photography - Intro to Film") == "Photography"
    assert _derive_category("Fitness - Yoga Fit") == "Fitness"
    assert _derive_category("Book Arts - Bookbinding") == "Book Arts"
    assert _derive_category("Pickleball - Beginner") == "Pickleball"
    # Biking is a standalone program, not a camp sub-activity, so it stays
    # even though Camp itself is removed.
    assert _derive_category("Biking - Tadpoles (Ages 4-5)") == "Biking"


def test_no_dash_in_name_is_uncategorized():
    assert _derive_category("Preschool Soccer") is None
