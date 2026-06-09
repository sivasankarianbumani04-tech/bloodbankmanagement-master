# Blood Bank Management System

## Overview

Blood Bank Management System is a web-based application developed using Django to efficiently manage blood donors, patients, blood stock, and blood requests. The system provides a centralized platform for blood banks and hospitals to maintain records, process requests, and monitor blood availability.

---

## Features

### Admin Module

* Manage donor records
* Manage patient records
* Approve or reject blood donations
* Approve or reject blood requests
* Monitor blood stock availability
* View request and donation history
* Access dashboard analytics and reports

### Donor Module

* Secure donor registration and login
* Blood donation request submission
* Blood request submission
* View donation history
* Track request approval status

### Patient Module

* Secure patient registration and login
* Submit blood requests
* View request history
* Track approval and fulfillment status

---

## Technologies Used

* Python
* Django
* HTML5
* CSS3
* Bootstrap
* SQLite
* Pandas

---

## Project Structure

```text
bloodbankmanagement/
│
├── blood/
├── donor/
├── patient/
├── templates/
├── static/
├── db.sqlite3
├── manage.py
└── requirements.txt
```

---

## Installation

### Clone the Repository

```bash
git clone https://github.com/sumitkumar1503/bloodbankmanagement.git
cd bloodbankmanagement
```

### Create Virtual Environment

```bash
python -m venv venv
```

### Activate Virtual Environment

Windows:

```bash
venv\Scripts\activate
```

Linux/Mac:

```bash
source venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Apply Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### Run the Server

```bash
python manage.py runserver
```

Open your browser and navigate to:

```text
http://127.0.0.1:8000/
```

---

## System Modules

### Administrator

* Manage donors and patients
* Handle blood requests
* Manage blood inventory
* Generate reports

### Donor

* Register and login
* Donate blood
* Request blood
* View personal history

### Patient

* Register and login
* Request blood units
* Track request status

---

## Database

The application uses SQLite as the default database. Django ORM is used for database operations and relationship management.

---

## Future Enhancements

* Email notifications
* SMS alerts
* Blood request prioritization
* Hospital integration
* Advanced analytics dashboard
* REST API support

---

## License

This project is intended for educational and academic purposes.

---

