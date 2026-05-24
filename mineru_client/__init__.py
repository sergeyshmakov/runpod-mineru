"""mineru_client — thin Python wrapper around a deployed mineru-runpod endpoint.

Usage:

    from mineru_client import MineruClient

    client = MineruClient(endpoint_id="...", api_key="...")
    result = client.parse_document(file_url="https://...", start_page=0, end_page=99)
    client.save_tarball(result, dest_dir="./out")

Accepts PDF, image (PNG/JPEG/GIF/BMP/TIFF/WebP), DOCX, PPTX, XLSX.
"""

from .client import MineruClient, MineruClientError

__all__ = ["MineruClient", "MineruClientError"]
