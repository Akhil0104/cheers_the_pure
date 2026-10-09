import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from app.models import Product, Category

# Create sample categories
categories = []
cat_names = ['Sport', 'Premium', 'Eco-Friendly', 'Professional']
for name in cat_names:
    cat, _ = Category.objects.get_or_create(name=name)
    categories.append(cat)

# Create sample products
products_data = [
    {'name': 'Sport 250ML', 'capacity': '250 ml', 'price': 2.99, 'is_featured': True, 'category': categories[0], 'description': 'Lightweight and compact bottle perfect for sports and fitness activities.'},
    {'name': 'Sport 500ML', 'capacity': '500 ml', 'price': 4.99, 'is_featured': True, 'category': categories[0], 'description': 'Ideal for daily hydration during workouts and outdoor activities.'},
    {'name': 'Premium 1L', 'capacity': '1000 ml', 'price': 12.99, 'is_featured': True, 'category': categories[1], 'description': 'Premium quality 1-liter bottle for professional use.'},
    {'name': 'Premium 2L', 'capacity': '2 litres', 'price': 18.99, 'is_featured': True, 'category': categories[1], 'description': 'Large capacity premium bottle for offices and events.'},
    {'name': 'Eco-Friendly 500ML', 'capacity': '500 ml', 'price': 6.99, 'is_featured': True, 'category': categories[2], 'description': 'Made from 100% recycled materials, perfect for eco-conscious brands.'},
    {'name': 'Professional 1L', 'capacity': '1000 ml', 'price': 9.99, 'is_featured': False, 'category': categories[3], 'description': 'Professional grade bottle for corporate events and branding.'},
]

for data in products_data:
    Product.objects.get_or_create(
        name=data['name'],
        defaults={
            'capacity': data['capacity'],
            'price': data['price'],
            'is_featured': data['is_featured'],
            'category': data['category'],
            'description': data['description'],
        }
    )

print("Products created successfully!")
