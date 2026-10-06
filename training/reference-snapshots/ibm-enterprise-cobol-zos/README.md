# IBM Enterprise COBOL for z/OS documentation

Downloaded from the [IBM documentation library](https://www.ibm.com/support/pages/enterprise-cobol-zos-documentation-library).

This collection covers the release sections from 3.1 through 6.5, including English and Japanese documents. It is tagged as **z/OS** material. Its compiler, runtime, and platform details must be distinguished from AS/400 and IBM i COBOL documentation.

## Files

- `documents/<release>/<language>/`: individual PDFs, BookManager files, and other document downloads.
- `archives/<release>/<language>/`: original IBM ZIP bundles.
- `extracted/<release>/<language>/`: documents extracted from those bundles, including any not individually linked in the library.
- `archive-metadata/`: preserved macOS resource-fork files separated from the extracted manuals; these are not PDFs and must not be indexed as documents.
- `pages/<release>/<language>/`: snapshots of linked HTML reference pages. Online documentation landing pages are snapshots, not complete offline mirrors of their interactive websites; the PDF manuals supply offline book content.
- `library.html`: the source library page used to enumerate the downloads.
- `manifest.json`: original and resolved URLs, titles, publication details, release/language references, local paths, byte counts, SHA-256 checksums, download outcomes, and archive contents.

The downloader inventories every external link within the library's release sections, deduplicates identical URLs, retrieves public announcement article bodies, and follows document attachments from directly linked IBM articles. A shared resource can have several release references in the manifest. Filenames include a URL hash to avoid collisions between editions. Retired BookManager links are recovered from IBM's alternate `publibfp.dhe.ibm.com` archive when available; the original link and actual mirror are both recorded.

The verified snapshot contains 290 downloaded resources and 90 actual documents extracted from ZIP bundles. Another 36 ZIP entries are macOS metadata, recorded separately in `excluded_archive_metadata`; they are not additional manuals. Extracted manuals can duplicate individual downloads.

## Resume or verify downloads

From the `agent-sql-alpha` directory:

```sh
python3 training/training_pipeline/download_ibm_cobol.py
```

The downloader requires Python 3, BeautifulSoup, lxml, and curl. It verifies HTTPS, resumes verified local files, retries failed resources, checks PDF signatures and ZIP integrity, and records failures instead of saving an error page as a manual. Existing snapshots are preserved when content changes. To enumerate a newer library revision, retain the existing `library.html` snapshot under a dated filename and download a fresh copy before rerunning.

IBM copyright and document-specific terms remain in the original files. The collection is downloaded reference material; it is not automatically included in model fine-tuning or the existing preparation pipeline's eligible training sources.
