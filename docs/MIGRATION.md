# Migration report

Sources: the August 2024 server backups of moca.virtual.museum (HostGator, plus an older 2022 IONOS copy) and mocadigitalart.com (IONOS). The live sites could not be crawled from the build machine, so anything changed online after August 2024 is not included.

## What was migrated
- 13,633 pages generated with 0 errors (1,062 of them AutoGallery galleries). Every old path is kept, lowercased, with `.asp` renamed to `.html`.
- 28,286 of 28,387 referenced images display. Every one of the 92,978 backup files is accounted for (published, merged as an older duplicate, or deliberately skipped).
- Text coverage is 99.74%. No page keeps less than 95% of its original words once navigation words are ignored.
- Media no page shows has its own pages under `/unlisted/`.
- Flash files play in the browser through the Ruffle emulator. Old video formats are converted to MP4, with the originals kept for download.

## Deliberately skipped (515 files)
- 201 server scripts (logins, guestbooks, forms).
- 266 editor, backup and test files.
- 48 drafts.
The list is in `build/skipped.json`.

## Could not be migrated
- 23 files exist only as iCloud placeholders on the backup machine (all in AutoGallery folders).
- 34 files are empty in every backup.
- About 86 media files are corrupt or cannot be decoded.
- 3,357 old image references point to files that are not in any backup.
- 28 internal links still point to retired login and guestbook scripts.

## Quality checks
- Browser QA found 0 JavaScript errors and no horizontal overflow on phones. The lightbox, slideshow, search, menu, Flash player and old-URL redirects all work.
- Desktop Core Web Vitals pass on all 16 pages tested.
- Mobile speed was improved with an 800 px image size, smaller 1600 px files, eager loading of the first images, asset versioning and media preconnect.
