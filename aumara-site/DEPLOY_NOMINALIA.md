# AUMARA — Nominalia / WordPress Deployment Runbook

## Current system map

- Domain: `elcidspain.com`
- Registrar / hosting provider: Nominalia / team.blue
- Customer code: `admin_elcid`
- CMS: WordPress hosted inside the Nominalia hosting space
- Public site: `https://elcidspain.com/`
- Target AUMARA route: `https://elcidspain.com/aumara`
- AUMARA source: `aumara-site/index.html` in this repository

The GitHub source is not automatically deployed to the live WordPress site. Publishing requires a deliberate copy into the Nominalia web root or conversion into a WordPress page/template.

## Renewal gate

1. Renew the current Domain Pack for one year.
2. Confirm the new expiry date is 16 July 2027.
3. Confirm the renewal preserves:
   - the domain;
   - current WordPress hosting;
   - SSL;
   - domain email services.
4. Update the account and domain contact email to `elcidspain@gmail.com`.
5. Enable 2FA / OTP and verify the recovery phone.

## Security gate before publishing

The existing WordPress installation has historical malware and plugin-error notices. Before changing production:

1. Download a full backup of the `www` web root.
2. Export the complete WordPress database.
3. Record the active PHP version, WordPress version, theme and plugins.
4. Create a new company-controlled WordPress administrator.
5. Create or rotate FTP/SFTP credentials.
6. Run a malware scan and inspect old upload/plugin folders.
7. Update WordPress core, active theme and plugins only after backup.
8. Remove or demote obsolete third-party users only after company access is confirmed.

## Recommended deployment path — static route

This is the fastest and least disruptive path for Google Ads.

1. Open Nominalia Control Panel.
2. Go to Web Hosting / FTP or File Manager.
3. Open the live document root, normally the `www` directory.
4. Create a physical directory named `aumara`.
5. Upload this repository file as:

   `www/aumara/index.html`

6. Confirm that WordPress rewrite rules do not override the physical directory.
7. Open `https://elcidspain.com/aumara/` in a private browser window.
8. Confirm HTTP 200, HTTPS, images, Booking.com CTA, email and phone links.
9. Add links to `/aumara/` from the current homepage and HOTEL section.

A physical directory is preferred for the first release because it does not depend on the old WordPress theme or page builder.

## Alternative deployment path — WordPress page

Use only if the site owner wants AUMARA fully inside the existing theme.

1. Recover or create a company-controlled WordPress admin.
2. Create a page with slug `aumara`.
3. Use a full-width / blank page template.
4. Port the HTML, CSS and JavaScript from `aumara-site/index.html` into a custom page template or approved HTML block.
5. Test for theme CSS and JavaScript conflicts.
6. Publish only after mobile and desktop QA.

## Asset hardening

The current v03 page references approved AUMARA images through Googleusercontent URLs. For a durable production release:

1. Download the approved images from the AUMARA Drive photo library.
2. Upload them to `www/aumara/assets/` or the WordPress Media Library.
3. Replace external image URLs with local HTTPS paths.
4. Compress large images to WebP where practical.
5. Keep descriptive alt text.

## Google Ads release gate

Do not reactivate advertising until all checks pass:

- `/aumara/` returns HTTP 200;
- no login, geo-block, bot challenge or redirect loop;
- AUMARA brand is visible;
- `EL CID VENTURES BENIDOLEIG S.L.` and CIF `B53816989` are visible;
- Booking.com is clearly described as an external booking/payment channel;
- all images and CTAs work;
- mobile and desktop layouts pass;
- Google Ads Final URL is changed to the owned page;
- the repaired ad becomes Eligible.

## Handover data required from previous maintainers

- current WordPress admin access;
- FTP/SFTP or Nominalia File Manager access;
- database access or export;
- active theme and plugin licences;
- GA4 property access;
- Search Console ownership;
- Google Tag Manager container access, if used;
- backup location and retention policy;
- list of third-party users and service accounts.
