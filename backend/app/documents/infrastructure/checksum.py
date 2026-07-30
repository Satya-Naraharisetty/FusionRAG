import hashlib

from app.documents.domain.interfaces import ChecksumGenerator


class SHA256ChecksumGenerator(ChecksumGenerator):
    def generate(self, content: bytes) -> str:
        """
        Generates a SHA-256 checksum string for binary content.
        """
        hasher = hashlib.sha256()
        hasher.update(content)
        return hasher.hexdigest()
