# Municipality Project Tracker - System Access Module (Setup Phase)

## Project Overview

This is a Django-based project for tracking municipality projects. This setup implements **Process 1: System Access Module** with the following components:

- Django project structure (Django 6.0.4)
- User authentication system (login/logout)
- Placeholder views for user management
- Basic template structure
- PostgreSQL database support

## Directory Structure

```
Gabaldon-Municipality-Project-Tracker/
├── config/                 # Django project settings
│   ├── settings.py        # Project settings (updated with core app)
│   ├── urls.py            # Main URL routing (updated)
│   ├── wsgi.py
│   └── asgi.py
├── core/                   # Core app for system access
│   ├── models.py          # Models (placeholder)
│   ├── views.py           # Views (authentication & user management)
│   ├── forms.py           # Forms (user creation, editing, filtering)
│   ├── urls.py            # App-level URL routing
│   ├── admin.py
│   ├── apps.py
│   └── migrations/
├── templates/             # Template directory
│   ├── base.html          # Base template (layout)
│   └── core/
│       ├── login.html     # Login page
│       ├── logout.html    # Logout confirmation
│       ├── admin_dashboard.html    # Admin dashboard
│       ├── user_list.html         # User list view
│       ├── user_form.html         # User create/edit form
│       └── user_confirm_delete.html # Delete confirmation
├── manage.py              # Django management script
└── requirements.txt       # Python dependencies

```

## Setup Instructions

### 1. Create Virtual Environment

```bash
python -m venv venv
```

### 2. Activate Virtual Environment

**On Windows:**
```bash
venv\Scripts\activate
```

**On macOS/Linux:**
```bash
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Database

Create a `.env` file in the project root (you can copy from `.env.example`) and set:
```bash
SECRET_KEY=replace-with-a-secure-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DB_NAME=gabaldon_db
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
```

If you prefer shell variables instead of a `.env` file:

**Windows (PowerShell):**
```powershell
$env:DB_NAME="gabaldon_db"
$env:DB_USER="postgres"
$env:DB_PASSWORD="your_password"
$env:DB_HOST="localhost"
$env:DB_PORT="5432"
```

**macOS/Linux:**
```bash
export DB_NAME=gabaldon_db
export DB_USER=postgres
export DB_PASSWORD=your_password
export DB_HOST=localhost
export DB_PORT=5432
```

### 5. Run Migrations

```bash
python manage.py migrate
```

### 6. Create Superuser (Admin)

```bash
python manage.py createsuperuser
```

Follow the prompts to create an admin user.

### 7. Run Development Server

```bash
python manage.py runserver
```

The application will be available at: `http://localhost:8000`

## Available URLs

- `/login/` - User login page
- `/logout/` - User logout (redirects to login)
- `/admin-dashboard/` - Admin dashboard (requires authentication)
- `/users/` - User list (requires authentication)
- `/users/create/` - Create new user (requires authentication)
- `/users/<id>/edit/` - Edit user (requires authentication)
- `/users/<id>/delete/` - Delete user (requires authentication)
- `/admin/` - Django admin panel

## Current Components

### Views (Placeholder Implementation)

1. **LoginView** - Handles user authentication
2. **LogoutView** - Logs out user and redirects to login
3. **AdminDashboardView** - Displays admin dashboard with user count
4. **UserListView** - Lists all users with pagination (10 per page)
5. **UserCreateView** - Form to create new users
6. **UserEditView** - Form to edit existing users
7. **UserDeleteView** - Confirmation page for user deletion

### Forms

1. **CustomUserCreationForm** - Creates new users with password validation
2. **CustomUserChangeForm** - Edits existing user information
3. **UserListFilterForm** - Placeholder for user search/filtering

### Templates

- **base.html** - Base layout with navigation
- **login.html** - Login form
- **logout.html** - Logout confirmation
- **admin_dashboard.html** - Dashboard with stats
- **user_list.html** - User list with pagination
- **user_form.html** - Create/edit user form
- **user_confirm_delete.html** - Delete confirmation

## Authentication System

The project uses Django's built-in authentication system with:
- User model: `django.contrib.auth.models.User`
- Login required mixins for protected views
- Session-based authentication
- CSRF protection

## Security Notes

⚠️ **Development Only Settings**
- `DEBUG = True` - Change to `False` for production
- `SECRET_KEY` - Generate a secure secret key for production
- `ALLOWED_HOSTS = []` - Add your domain for production

## Next Steps

### For Full Implementation (Future):

1. **Create Custom User Model** - Extend Django's User model if needed
2. **Add Role-Based Access Control** - Use Django Groups for Admin/Staff roles
3. **Implement CRUD Logic** - Add full business logic to views
4. **Add Project Module** - Track municipality projects
5. **Add Reports Module** - Generate project reports
6. **Styling** - Add CSS framework (Bootstrap, Tailwind, etc.)
7. **API Development** - Create REST API endpoints
8. **Testing** - Add unit and integration tests

## Important Notes

✓ This setup creates the **structure only** - no full business logic yet
✓ All views are placeholder implementations
✓ Uses Django's built-in User model
✓ Modular design for easy expansion
✓ Ready for Phase 2 implementation

## Troubleshooting

### Database Connection Error
- Ensure PostgreSQL is running
- Verify database credentials in `config/settings.py`
- Check PostgreSQL is listening on correct port (5432)

### Django Import Error
- Activate virtual environment
- Install requirements: `pip install -r requirements.txt`

### Migration Errors
- Delete `db.sqlite3` if using SQLite
- Run `python manage.py migrate --fake-initial` if needed

## Support

For issues or questions, refer to:
- Django Documentation: https://docs.djangoproject.com/
- PostgreSQL Documentation: https://www.postgresql.org/docs/
