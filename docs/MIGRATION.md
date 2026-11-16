# Migration report

Sources: the August 2024 server backups of moca.virtual.museum (HostGator, plus an older 2022 IONOS copy) and mocadigitalart.com (IONOS). The live sites could not be crawled from the build machine, so the build was then compared with the live sites' GitHub repos (lily-codes-4u/moca and lily-codes-4u/mocadigitalart, July 2026). Their media matches the backups except for: 18 correctly named copies of AI images that fix misspelled image links (added), 2 pages found only in the repo, ainatur/ainatur01.htm and kuns/kuns01a.htm (added), placeholder copies in donnie2010/2011/2014/2017 and open/spiazzi that reuse other images (not used, the real images from the backups are kept), MP4 re-encodes of digivid videos (not needed, the site makes its own), and duplicate "name 2.htm" pages (skipped).

## What was migrated
- 13,635 pages generated with 0 errors (1,062 of them AutoGallery galleries). Every old path is kept, lowercased, with `.asp` renamed to `.html`.
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
- 3,336 old image references point to files that are not in any backup.
- 28 internal links still point to retired login and guestbook scripts.

## Quality checks
- Browser QA found 0 JavaScript errors and no horizontal overflow on phones. The lightbox, slideshow, search, menu, Flash player and old-URL redirects all work.
- Desktop Core Web Vitals pass on all 16 pages tested.
- Mobile speed was improved with an 800 px image size, smaller 1600 px files, eager loading of the first images, asset versioning and media preconnect.
