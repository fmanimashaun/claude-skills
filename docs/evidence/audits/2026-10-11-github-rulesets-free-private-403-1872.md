# GitHub rulesets on a private repository without a paid plan — captured 2026-10-11 (#1872)

Command: `gh api -i repos/<free-org>/<private-repo>/rulesets` (read-only GET), gh 2.102.0, organization plan `free`.
The REST docs list only 200/404/500 for this endpoint; this 403 is measured, not documented.

```
HTTP/2.0 403 Forbidden
X-Github-Api-Version-Selected: 2022-11-28
{"message":"Upgrade to GitHub Pro or make this repository public to enable this feature.","documentation_url":"https://docs.github.com/rest/repos/rules#get-all-repository-rulesets","status":"403"}
stderr: gh: Upgrade to GitHub Pro or make this repository public to enable this feature. (HTTP 403)
exit: 1
```
