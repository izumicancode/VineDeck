from vinedeck.core.library import LibraryQuery, filter_and_sort
from vinedeck.database.models import Application


def A(i, name, **kw):
    return Application(id=i, name=name, executable_path="/x.exe", created_at=f"2024-01-0{i}", sort_order=i, **kw)


APPS = [
    A(1, "Zelda", category_name="Games", category_id=1, description="adventure", launch_count=3, last_played="2024-05-01"),
    A(2, "alpha tool", category_name="Utilities", category_id=3, favorite=True),
    A(3, "Beta", category_name="Games", category_id=1, launch_count=9, last_played="2024-06-01"),
]


def names(q):
    return [a.name for a in filter_and_sort(APPS, q)]


def test_sorting():
    assert names(LibraryQuery(sort_key="name")) == ["alpha tool", "Beta", "Zelda"]
    assert names(LibraryQuery(sort_key="name", reverse=True)) == ["Zelda", "Beta", "alpha tool"]
    assert names(LibraryQuery(sort_key="added")) == ["Beta", "alpha tool", "Zelda"]
    assert names(LibraryQuery(sort_key="played")) == ["Beta", "Zelda", "alpha tool"]
    assert names(LibraryQuery(sort_key="count")) == ["Beta", "Zelda", "alpha tool"]
    assert names(LibraryQuery(sort_key="category")) == ["Beta", "Zelda", "alpha tool"]
    assert names(LibraryQuery(sort_key="custom")) == ["Zelda", "alpha tool", "Beta"]


def test_sections_and_search():
    assert names(LibraryQuery(section="favorites")) == ["alpha tool"]
    assert names(LibraryQuery(section="category", category_id=1)) == ["Beta", "Zelda"]
    assert names(LibraryQuery(section="recent")) == ["Beta", "Zelda"]
    assert names(LibraryQuery(section="most_played")) == ["Beta", "Zelda"]
    assert names(LibraryQuery(text="ZEL")) == ["Zelda"]
    assert names(LibraryQuery(text="utilities")) == ["alpha tool"]       # category
    assert names(LibraryQuery(text="adventure")) == ["Zelda"]            # description
    assert names(LibraryQuery(text="games beta")) == ["Beta"]            # all words must match
    assert names(LibraryQuery(text="nothing")) == []
