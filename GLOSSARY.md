# SaveOnGames

A site that compares what Portuguese stores charge for games and consoles, with a marketplace for used copies and a place for people to keep their game collections.

## Language

### Catalogue and prices

**Store**:
A Portuguese shop website whose catalogue the daily run reads.
_Avoid_: shop, retailer, seller

**Game**:
One title on one platform. The PS5 and Switch versions of a title are two games.
_Avoid_: product, title (for the whole thing)

**Edition**:
A version of a game sold as its own product, such as Standard, Day One Edition or Game Key Card. Prices, wishes and the copies people own or sell all belong to an edition.
_Avoid_: version, variant, SKU

**Offer**:
One store's page for an edition, new or used, with its price and stock.
_Avoid_: product, listing

**Console**:
Hardware a store sells next to its games, grouped into editions and offers like a game. Controllers and other accessories are left out.
_Avoid_: hardware, accessory

**Code in a box**:
A game sold as a download code inside a box ("Código na caixa"). It is never tracked.

**Price history**:
The prices an offer has had, recorded each time its price or stock changed.

**Crossed-out price**:
The "was" price a store shows beside its own price. It is recorded and never trusted.
_Avoid_: old price, original price

**Real discount**:
A price lower than the lowest price of the 30 days before it, on an offer watched for those 30 days.
_Avoid_: sale price, promotion

**Historical low**:
The lowest price a new, in-stock copy of an edition has ever had, at any store.
_Avoid_: all-time low, best price ever

**Card**:
A game's tile in the catalogue and on the home page. One card can gather a game the stores name differently on different platforms.

### Reading the stores

**Daily run**:
The scheduled reading of the stores into the database, followed by game information and the wishlist alerts.
_Avoid_: scrape, crawl, cron job

**Full run**:
The morning daily run: every store, product pages included, then IGDB and the wishlist alerts.

**Light run**:
The evening daily run: only the listing pages of Press Start, Mega Mania and Gaming Replay.

**Blocked store**:
A store that refused our requests (403 or 429). The daily run leaves it alone for 24 hours.

**Match**:
The link from an offer to its game and edition, worked out from the name the store gives it.

**Pinned match**:
A match a moderator set by hand. The daily run and later rematches keep it.

**Match-only store**:
A store whose offers can join known games and editions but never create new ones. Rádio Popular is one.

**Merge**:
Folding a duplicate game or edition into another. Old links, listings, collection items and reviews move to the one kept.

**Possible duplicate**:
Two games that may be one game written differently by two stores, listed for a moderator to merge or dismiss.

**IGDB**:
The outside game database that supplies summaries, genres, covers, trailers, scores and DLC lists.

### Marketplace

**Listing**:
A used copy a user puts up for sale, with photos.
_Avoid_: ad, offer

**Conversation**:
The messages between one buyer and the seller about one listing.
_Avoid_: chat, thread

**Purchase**:
The steps of buying a listing inside its conversation: requested, accepted, sent, completed, or else declined, cancelled or problem.
_Avoid_: order, transaction

**Rating**:
The 1 to 5 stars each side of a completed purchase gives the other.
_Avoid_: feedback, score

### People's games

**Collection**:
The editions a user owns ("Tenho"), with format, play status, hours and notes.
_Avoid_: library

**Wish**:
An edition a user wants ("Quero"). It remembers the best price when it was added and may have a target price. The user's wishes are their wishlist.
_Avoid_: favourite

**Target price**:
The price a user is waiting for on a wish.

**Good deal**:
A wish that is on a real discount, at its historical low, cheaper than when it was added, or at its target price. The header's bell counts them.

**Wishlist alert**:
An e-mail after the full run listing the wishes that changed: on sale, back in stock, a used copy for sale, a price drop or a target price reached.

**Review**:
A user's score of a game from 1 to 10, with optional text.
_Avoid_: rating

**Follow**:
One user keeping track of another's public profile and collection. It is one way and sends no notice.

### People

**Moderator**:
A user who handles reports and fixes matches.

**Admin**:
A moderator who can also name and remove moderators.

**Report**:
A user's flag on a listing, a user, a rating or a review, for moderators to act on.
_Avoid_: complaint, flag
