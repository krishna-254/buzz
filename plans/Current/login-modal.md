# Plan: In-App Login Modal

## Goal
Replace the redirect to Frappe's `/login` page with an in-app modal dialog that supports all login features. Users stay on the current page (booking, custom form, etc.) and authenticate without leaving context.

## Frappe APIs (all `allow_guest=True`)

| Feature | Endpoint | Params |
|---------|----------|--------|
| Login | `POST /api/v2/method/login` | `usr`, `pwd` |
| Sign up | `POST /api/v2/method/frappe.core.doctype.user.user.sign_up` | `email`, `full_name`, `redirect_to` |
| Forgot password | `POST /api/v2/method/frappe.core.doctype.user.user.reset_password` | `user` (email) |
| Email link login | `POST /api/v2/method/frappe.www.login.send_login_link` | `email` |
| Social login providers | `GET /api/v2/method/frappe.client.get_list` on `Social Login Key` | `filters`, `fields` |
| OAuth authorize URL | Not whitelisted — need a custom wrapper API |

## Architecture

### New Files
1. **`dashboard/src/components/LoginDialog.vue`** — Main modal component with multi-view state machine
2. **`dashboard/src/composables/useLoginDialog.ts`** — Shared composable to open/close the dialog from anywhere
3. **`buzz/api/auth.py`** — New whitelisted API `get_login_context` (returns Google OAuth URL, settings flags)

### Modified Files
1. **`dashboard/src/components/LoginRequired.vue`** — Change "Log In" button to open modal instead of redirect
2. **`dashboard/src/data/session.ts`** — Add resources for signup, forgot password, email link login
3. **`dashboard/src/router.ts`** — Replace `window.location.href` redirect with showing `LoginRequired` state (no more redirect to Frappe's `/login`)
4. **`dashboard/src/App.vue`** — Mount `LoginDialog` at app root level so it's available everywhere
5. **`buzz/buzz/doctype/buzz_settings/buzz_settings.json`** — Add new "Login" tab with `login_banner` Markdown Editor field

## Implementation Steps

### Step 1: Backend API — `get_login_context`

Create new file `buzz/api/auth.py`:

```python
@frappe.whitelist(allow_guest=True)
def get_login_context():
    """Return login configuration for the frontend modal."""
    from frappe.utils.oauth import get_oauth2_authorize_url, get_oauth_keys

    context = {
        "disable_signup": cint(frappe.get_website_settings("disable_signup")),
        "disable_user_pass_login": cint(frappe.get_system_settings("disable_user_pass_login")),
        "login_with_email_link": cint(frappe.get_system_settings("login_with_email_link")),
        "login_banner": frappe.db.get_single_value("Buzz Settings", "login_banner") or "",
        "google_login": None,
    }

    # Only fetch Google provider
    google = frappe.db.get_value(
        "Social Login Key",
        {"enable_social_login": 1, "provider_name": "Google"},
        ["name", "client_id", "base_url"],
        as_dict=True,
    )

    if google and google.client_id and google.base_url and get_oauth_keys(google.name):
        redirect_to = frappe.utils.get_url("/dashboard")
        context["google_login"] = {
            "auth_url": get_oauth2_authorize_url(google.name, redirect_to),
        }

    return context
```

### Step 2: Composable — `useLoginDialog.ts`

Simple reactive state to control the modal from anywhere:

```typescript
import { ref } from "vue"

const isOpen = ref(false)
const onSuccessCallback = ref<(() => void) | null>(null)

export function useLoginDialog() {
    function open(onSuccess?: () => void) {
        onSuccessCallback.value = onSuccess || null
        isOpen.value = true
    }

    function close() {
        isOpen.value = false
        onSuccessCallback.value = null
    }

    return { isOpen, open, close, onSuccessCallback }
}
```

### Step 3: `LoginDialog.vue` — Multi-View Modal

Uses frappe-ui `Dialog` component. Internal state machine with 4 views:

**Views:**
1. **`login`** — Email + password fields, Login button, "Forgot Password?" link, social login buttons, "Login with Email Link" button, "Don't have an account? Sign up" link
2. **`signup`** — Full name + email fields, Sign up button, "Have an account? Login" link
3. **`forgot-password`** — Email field, "Reset Password" button, "Back to Login" link
4. **`email-link`** — Email field, "Send Login Link" button, "Back to Login" link

Each view shows a success/error message area. All use frappe-ui components (`FormControl`, `Button`, `Dialog`).

**Component structure:**
```
<Dialog v-model="isOpen" :options="{ size: 'sm' }">
  <template #body-main>
    <!-- Banner from Buzz Settings (shown once per content change) -->
    <!-- Stored in localStorage as hash of content. If admin updates banner, hash changes → shown again -->
    <div v-if="showBanner" v-html="loginContext.login_banner" class="prose" />

    <!-- login view -->
    <div v-if="currentView === 'login'">
      <FormControl label="Email" type="email" v-model="email" />
      <FormControl label="Password" type="password" v-model="password" />
      <div class="text-right">
        <Button variant="ghost" @click="currentView = 'forgot-password'">Forgot Password?</Button>
      </div>
      <Button variant="solid" class="w-full" @click="handleLogin" :loading="loginLoading">Login</Button>

      <!-- social login divider + buttons (conditional on providers) -->
      <div v-if="providers.length" class="divider">or</div>
      <Button v-for="p in providers" @click="socialLogin(p)" class="w-full">
        Login with {{ p.provider_name }}
      </Button>

      <!-- email link (conditional on setting) -->
      <Button v-if="emailLinkEnabled" @click="currentView = 'email-link'" class="w-full">
        Login with Email Link
      </Button>

      <!-- signup link -->
      <div v-if="!disableSignup" class="text-center">
        Don't have an account? <Button variant="ghost" @click="currentView = 'signup'">Sign up</Button>
      </div>
    </div>

    <!-- signup view -->
    <div v-if="currentView === 'signup'">...</div>

    <!-- forgot-password view -->
    <div v-if="currentView === 'forgot-password'">...</div>

    <!-- email-link view -->
    <div v-if="currentView === 'email-link'">...</div>
  </template>
</Dialog>
```

**API calls:**
- Login: `POST login` with `usr`/`pwd` → on success, reload user resource, close dialog, call `onSuccessCallback`
- Sign up: `POST frappe.core.doctype.user.user.sign_up` → show success message ("Check your email")
- Forgot password: `POST frappe.core.doctype.user.user.reset_password` → show success message
- Email link: `POST frappe.www.login.send_login_link` → show success message
- Social login: `window.location.href = provider.auth_url` (OAuth requires full redirect)

### Step 4: Mount in App.vue

Add `<LoginDialog />` to `App.vue` so it's available globally without each page importing it.

### Step 5: Update LoginRequired.vue

Replace `redirectToLogin()` with `useLoginDialog().open()`. After successful login, the page re-renders with authenticated state.

## Design Details

- Dialog size: `sm` (matches Frappe's login card width)
- Use Tailwind CSS variables: `bg-surface-modal`, `text-ink-gray-8`, `border-outline-gray-2`
- Form spacing: `space-y-4` between fields
- Social login buttons: outline style with provider icon
- Error messages: red text below the form using `text-red-600`
- Success messages: green text using `text-green-600`
- All text uses `__()` for translation
- No Frappe logo/branding in the modal — clean, minimal
- **Banner persistence**: Hash the banner content, store in `localStorage` as `login_banner_seen`. Only show banner if stored hash doesn't match current content hash. When admin updates the banner, hash changes → banner re-appears for all users

## Notes

1. **Social login redirect**: OAuth requires a full page redirect to Google. After auth, Frappe redirects back to `/dashboard`. This is how all OAuth works — no way around it.

2. **Router guard behavior**: Protected routes still show `LoginRequired.vue` with the "Login Required" message + button. Clicking the button opens the login modal instead of redirecting. On successful login, the page re-renders with authenticated state.
