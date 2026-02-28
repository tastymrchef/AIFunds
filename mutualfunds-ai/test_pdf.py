import fitz  # PyMuPDF
import requests
import tempfile

# Download the PDF
url = "https://amc.ppfas.com/downloads/factsheet/2026/ppfas-mf-factsheet-for-January-2026.pdf"
response = requests.get(url, timeout=30)

tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
tmp.write(response.content)
tmp.close()

# Open and read first 3 pages
doc = fitz.open(tmp.name)

print(f"Total pages: {len(doc)}")
print("\n=== PAGE 1 ===")
print(doc[0].get_text())
print("\n=== PAGE 2 ===")
print(doc[1].get_text())
print("\n=== PAGE 3 ===")
print(doc[2].get_text())
print("\n=== PAGE 10 (Flexi Cap) ===")
print(doc[9].get_text())  # page 10 = index 9
print("\n=== PAGE 11 ===")
print(doc[10].get_text())
print("\n=== PAGE 12 ===")
print(doc[11].get_text())