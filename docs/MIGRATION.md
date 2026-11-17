# Migration report

Sources: the August 2024 server backups of moca.virtual.museum (HostGator, plus an older 2022 IONOS copy) and mocadigitalart.com (IONOS). The live sites could not be crawled from the build machine, so the build was then compared with the live sites' GitHub repos (lily-codes-4u/moca and lily-codes-4u/mocadigitalart, July 2026). Their media matches the backups except for: 18 correctly named copies of AI images that fix misspelled image links (added), 2 pages found only in the repo, ainatur/ainatur01.htm and kuns/kuns01a.htm (added), placeholder copies in donnie2010/2011/2014/2017 and open/spiazzi that reuse other images (not used, the real images from the backups are kept), MP4 re-encodes of digivid videos (not needed, the site makes its own), and duplicate "name 2.htm" pages (skipped).

A second check in November 2026 compared every page of both repos (13,091 pages plus 33,046 static AutoGallery views) with the built site, and spot-checked about 300 live URLs (the repos match what the live sites serve). Pages whose live copy has content the backup copy lacked are kept in `overrides/` and replace the backup copy at build time: the artist credit on 18 Vestments pages, artwork on 13 Don Archer pages, Images of the Day issues 104-108, and two 2023 AutoGalleries in the 3D Rendered list. Two spam pages planted on the old server and one spam link were removed. "Click to play" links to old video files now open the MP4 copies, as on the live sites.

## What was migrated
- 13,635 pages generated with 0 errors (1,062 of them AutoGallery galleries). Every old path is kept, lowercased, with `.asp` renamed to `.html`.
- 28,286 of 28,387 referenced images display. Every one of the 92,978 backup files is accounted for (published, merged as an older duplicate, or deliberately skipped).
- Text coverage is 99.74%. No page keeps less than 95% of its original words once navigation words are ignored.
- Media no page shows has its own pages under `/unlisted/` (a file stored again under another name is shown once, and not there when a page shows its twin).
- Duplicate pages (the `/donnie(s)/` mirror, `x.htm`/`x.html` twins, Finder copy folders, folders copied into other folders, draft names such as `indexx.html`, Images of the Day issues saved under two numbers) are kept once. Every other copy is a small redirect page at its old address, left out of hubs, the directory, search and the sitemap; anything a copy showed that the kept page lacked was added to it first. `tools/dedupe.py` does this at the end of the build, `tools/duplicates.tsv` holds the decisions made by hand, `tools/media_twins.tsv` the media stored twice, and `build/duplicates.json` lists the redirects and the near-copies left for a person to judge.
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
