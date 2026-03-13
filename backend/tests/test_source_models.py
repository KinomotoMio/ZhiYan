import pytest
from app.models.source import detect_file_category, FileCategory

@pytest.mark.parametrize("filename, expected_category", [
    ("document.pdf", FileCategory.PDF),
    ("report.docx", FileCategory.DOCX),
    ("report.doc", FileCategory.DOCX),
    ("notes.md", FileCategory.MARKDOWN),
    ("notes.markdown", FileCategory.MARKDOWN),
    ("presentation.pptx", FileCategory.PPTX),
    ("presentation.ppt", FileCategory.PPTX),
    ("image.png", FileCategory.IMAGE),
    ("photo.jpg", FileCategory.IMAGE),
    ("graphic.jpeg", FileCategory.IMAGE),
    ("animation.gif", FileCategory.IMAGE),
    ("web_image.webp", FileCategory.IMAGE),
    ("data.txt", FileCategory.TEXT),
    ("spreadsheet.csv", FileCategory.TEXT),
    ("config.json", FileCategory.TEXT),
    # Case sensitivity
    ("DOCUMENT.PDF", FileCategory.PDF),
    ("PHOTO.JPG", FileCategory.IMAGE),
    # Multiple dots
    ("archive.tar.gz", FileCategory.UNKNOWN),
    ("document.v1.pdf", FileCategory.PDF),
    # No extension
    ("README", FileCategory.UNKNOWN),
    # Unknown extension
    ("script.sh", FileCategory.UNKNOWN),
    # Edge cases
    ("", FileCategory.UNKNOWN),
    (".", FileCategory.UNKNOWN),
    (".gitignore", FileCategory.UNKNOWN), # Path(".gitignore").suffix is ""
])
def test_detect_file_category(filename, expected_category):
    assert detect_file_category(filename) == expected_category
