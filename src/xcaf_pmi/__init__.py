"""Read the GD&T in an OpenCascade XCAF document and write its geometry as STEP without PMI."""

from xcaf_pmi.reader import FORMAT, export_step, open_document, read

__all__ = ["FORMAT", "export_step", "open_document", "read"]
