# Tailwind CSS Setup for ClinicalRecordsService

## Overview
This document describes the Tailwind CSS setup for the ClinicalRecordsService, which provides a comprehensive styling system for the clinical records management interface.

## Files Structure
```
ClinicalRecordsService/
├── package.json                 # npm dependencies and build scripts
├── tailwind.config.js          # Tailwind configuration
├── clinical_records/static/clinical_records/css/
│   ├── input.css               # Source CSS with Tailwind directives
│   └── tailwind.min.css        # Generated CSS (minified)
└── build_css.bat               # Windows batch file for easy rebuilding
```

## Setup Instructions

### 1. Install Dependencies
```bash
npm install
```

### 2. Build CSS
```bash
npm run build
```

### 3. Development Mode (Watch for changes)
```bash
npm run watch
```

### 4. Windows Quick Build
Double-click `build_css.bat` or run:
```bash
build_css.bat
```

## Configuration

### Tailwind Config (`tailwind.config.js`)
- **Content Paths**: Scans HTML templates, JS files, and Python files for class usage
- **Custom Colors**: Primary and secondary color palettes
- **Custom Fonts**: System font stack
- **Plugins**: Currently none, but extensible

### Input CSS (`input.css`)
Contains:
- Tailwind base, components, and utilities
- Custom component classes (buttons, forms, cards, etc.)
- Custom utility classes
- Responsive design utilities

## Custom Components

### Buttons
- `.btn` - Base button styles
- `.btn-primary` - Primary action button
- `.btn-secondary` - Secondary action button
- `.btn-danger` - Destructive action button
- `.btn-success` - Success action button

### Forms
- `.form-input` - Input field styling
- `.form-label` - Label styling

### Cards
- `.card` - Base card container
- `.card-header` - Card header section
- `.card-body` - Card content section
- `.card-footer` - Card footer section

### Navigation
- `.nav-link` - Navigation link styling
- `.nav-link-active` - Active navigation state
- `.nav-link-inactive` - Inactive navigation state

### Tables
- `.table` - Base table styling
- `.table-header` - Table header section
- `.table-header-cell` - Header cell styling
- `.table-body` - Table body section
- `.table-row` - Table row styling
- `.table-cell` - Table cell styling

### Badges
- `.badge` - Base badge styling
- `.badge-success` - Success badge
- `.badge-warning` - Warning badge
- `.badge-danger` - Danger badge
- `.badge-info` - Info badge

### Alerts
- `.alert` - Base alert styling
- `.alert-success` - Success alert
- `.alert-warning` - Warning alert
- `.alert-danger` - Danger alert
- `.alert-info` - Info alert

### Modals
- `.modal` - Modal container
- `.modal-overlay` - Modal backdrop
- `.modal-content` - Modal content area

### Utilities
- `.loading-spinner` - Loading animation
- `.dropdown` - Dropdown container
- `.dropdown-menu` - Dropdown menu
- `.dropdown-item` - Dropdown item

## Usage in Templates

### Basic Example
```html
{% load static %}
<link rel="stylesheet" href="{% static 'clinical_records/css/tailwind.min.css' %}">

<div class="card">
    <div class="card-header">
        <h2 class="text-xl font-bold">Clinical Records</h2>
    </div>
    <div class="card-body">
        <button class="btn btn-primary">Save Record</button>
        <button class="btn btn-secondary">Cancel</button>
    </div>
</div>
```

### Form Example
```html
<form class="space-y-4">
    <div>
        <label class="form-label">Patient Name</label>
        <input type="text" class="form-input" placeholder="Enter patient name">
    </div>
    <div class="flex space-x-4">
        <button type="submit" class="btn btn-primary">Submit</button>
        <button type="button" class="btn btn-secondary">Reset</button>
    </div>
</form>
```

## Development Workflow

1. **Make Changes**: Edit `input.css` to add/modify styles
2. **Build CSS**: Run `npm run build` to generate new CSS
3. **Test**: Refresh browser to see changes
4. **Watch Mode**: Use `npm run watch` for automatic rebuilding during development

## Troubleshooting

### Common Issues

1. **CSS not updating**: Make sure to run `npm run build` after changes
2. **Classes not working**: Check if the class is included in the content paths in `tailwind.config.js`
3. **Build errors**: Check for syntax errors in `input.css`

### Performance
- The generated CSS is minified for production
- Only used classes are included (purged)
- File size is optimized for fast loading

## Integration with Django

The CSS is served through Django's static file system:
- Files are in `clinical_records/static/clinical_records/css/`
- Referenced in templates using `{% static 'clinical_records/css/tailwind.min.css' %}`
- Django's `collectstatic` command will include these files

## Customization

To add new styles:
1. Edit `input.css` in the appropriate `@layer` section
2. Use `@apply` directive to compose Tailwind utilities
3. Run `npm run build` to regenerate CSS
4. Test in browser

## Maintenance

- Keep Tailwind CSS updated: `npm update tailwindcss`
- Update browserslist database: `npx update-browserslist-db@latest`
- Review unused styles periodically
- Test across different browsers and devices

