import csv
import os
from question.models import Question  # Replace 'your_app' with your app name

# Path where your CSV files are stored
csv_folder_path = 'question\csv_files'

# Loop over all CSV files
for filename in os.listdir(csv_folder_path):
    if filename.endswith('.csv'):
        # Extract year from filename (assuming '2015.csv', '2016.csv', etc.)
        year_part = filename.split('.')[0]
        try:
            year = int(year_part)
        except ValueError:
            print(f"Skipping file {filename} because year could not be determined.")
            continue

        file_path = os.path.join(csv_folder_path, filename)
        
        with open(file_path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                Question.objects.create(
                    source_type='PYQ',
                    year=year,
                    subject=row['Subject'],
                    topic=None,
                    subtopic=None,
                    question_html=row['Question_HTML'],
                    option_a=row['Option_A'],
                    option_b=row['Option_B'],
                    option_c=row['Option_C'],
                    option_d=row['Option_D'],
                    correct_option=row['Correct Option'],
                    difficulty_level=row['Difficulty Level'],
                    nature=row['Nature'],
                    explanation_html=row['Explanation_HTML'],
                )

        print(f"✅ Imported questions for year {year}")

print("🎯 All CSV files processed successfully!")