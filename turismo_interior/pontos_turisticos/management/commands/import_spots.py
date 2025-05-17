import csv
import os
from django.core.management.base import BaseCommand
from django.db import transaction
from pontos_turisticos.models import TouristSpot, Type, CityType

class Command(BaseCommand):
    help = 'Importa pontos turísticos do CSV de forma otimizada'
    
    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str, help='Caminho para o arquivo CSV')
        parser.add_argument('--clear', action='store_true', help='Limpar banco antes de importar')
    
    def clean_coordinate(self, coord_str):
        """Remove pontos extras e converte vírgula para ponto como separador decimal."""
        if not coord_str:
            return 0.0
        
        # Remove todos os pontos e substitui vírgula por ponto
        # Depois converte para float
        clean_str = coord_str.replace('.', '').replace(',', '.')
        
        # Se o número é negativo, precisamos restaurar o sinal
        if coord_str.startswith('-'):
            clean_str = '-' + clean_str.lstrip('-')
        
        try:
            return float(clean_str)
        except ValueError:
            # Se ainda falhar, tenta uma abordagem mais agressiva
            import re
            # Extrai apenas dígitos, ponto e sinal negativo
            digits = re.sub(r'[^\d.-]', '', clean_str)
            # Garante que há apenas um ponto decimal
            parts = digits.split('.')
            if len(parts) > 1:
                digits = parts[0] + '.' + ''.join(parts[1:])
            return float(digits) if digits else 0.0
    
    @transaction.atomic
    def handle(self, *args, **kwargs):
        csv_path = kwargs['csv_path']
        clear_db = kwargs.get('clear', False)
        
        if not os.path.exists(csv_path):
            self.stdout.write(self.style.ERROR(f'Arquivo não encontrado: {csv_path}'))
            return

        self.stdout.write('Iniciando importação...')
        
        # Limpar banco de dados se solicitado
        if clear_db:
            self.stdout.write('Limpando banco de dados...')
            CityType.objects.all().delete()
            TouristSpot.objects.all().delete()
            Type.objects.all().delete()
            self.stdout.write('Banco de dados limpo!')
        
        # Verificação antes de criar objetos
        existing_place_ids = set(TouristSpot.objects.values_list('place_id', flat=True))
        
        # Primeiro, coletar todos os tipos únicos e verificar duplicatas
        type_names = set()
        spots_data = []
        place_ids_in_csv = set()
        duplicates_in_csv = set()
        
        with open(csv_path, encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                place_id = row['Place_ID']
                if place_id in place_ids_in_csv:
                    duplicates_in_csv.add(place_id)
                    continue  # Pular duplicatas no próprio CSV
                place_ids_in_csv.add(place_id)
                
                # Limpar e normalizar os tipos
                try:
                    types = [t.strip() for t in row['Tipos'].split(',') if t.strip()]
                    if not types:  # Se não houver tipos, pule
                        continue
                    type_names.update(types)
                    spots_data.append({
                        'data': row,
                        'types': types
                    })
                except KeyError:
                    self.stdout.write(self.style.WARNING(f"Erro: Coluna 'Tipos' não encontrada na linha: {row}"))
                    continue
        
        if duplicates_in_csv:
            self.stdout.write(f"AVISO: {len(duplicates_in_csv)} place_ids duplicados no CSV: {list(duplicates_in_csv)[:5]}...")
            
        if existing_place_ids:
            duplicate_with_db = place_ids_in_csv.intersection(existing_place_ids)
            if duplicate_with_db:
                self.stdout.write(f"AVISO: {len(duplicate_with_db)} place_ids já existem no banco: {list(duplicate_with_db)[:5]}...")
        
        self.stdout.write(f'Encontrados {len(type_names)} tipos únicos')
        
        # Criar tipos em bulk
        Type.objects.bulk_create(
            [Type(name=name) for name in type_names],
            ignore_conflicts=True
        )
        
        # Mapear nomes de tipos para objetos Type
        type_map = {t.name: t for t in Type.objects.all()}
        
        # Criar spots em bulk (apenas os que não existem)
        spots = []
        for spot_info in spots_data:
            row = spot_info['data']
            if row['Place_ID'] in existing_place_ids:
                continue  # Pular registros que já existem
                
            try:
                spot = TouristSpot(
                    name=row['Nome'],
                    address=row['Endereço'],
                    city=row['Cidade'],
                    rating=float(row['Avaliação'].replace(',', '.')) if row['Avaliação'] else 0.0,
                    latitude=self.clean_coordinate(row['Latitude']),
                    longitude=self.clean_coordinate(row['Longitude']),
                    place_id=row['Place_ID']
                )
                spots.append(spot)
            except (ValueError, KeyError) as e:
                self.stdout.write(self.style.WARNING(f'Erro ao processar linha: {e}, valores: lat={row.get("Latitude", "")}, lng={row.get("Longitude", "")}'))
                continue
        
        if not spots:
            self.stdout.write(self.style.WARNING('Nenhum novo ponto turístico para importar.'))
            return
            
        self.stdout.write(f'Importando {len(spots)} pontos turísticos...')
        
        # Usar ignore_conflicts para evitar falhas por violação de unicidade
        try:
            TouristSpot.objects.bulk_create(spots, ignore_conflicts=True)
        except Exception as e:
            # Se não suportar ignore_conflicts (Django < 2.2), usar uma abordagem alternativa
            self.stdout.write(self.style.WARNING(f'Erro no bulk_create, tentando importação individual: {e}'))
            
            for spot in spots:
                try:
                    if not TouristSpot.objects.filter(place_id=spot.place_id).exists():
                        spot.save()
                except Exception as inner_e:
                    self.stdout.write(self.style.WARNING(f'Erro ao salvar {spot.name}: {inner_e}'))
        
        # Buscar os spots recém-criados para adicionar tipos
        imported_place_ids = [spot.place_id for spot in spots]
        created_spots = {spot.place_id: spot for spot in TouristSpot.objects.filter(place_id__in=imported_place_ids)}
        
        # Adicionar tipos aos spots
        for spot_info in spots_data:
            place_id = spot_info['data']['Place_ID']
            if place_id in created_spots:
                spot = created_spots[place_id]
                types = [type_map[t] for t in spot_info['types'] if t in type_map]
                try:
                    spot.types.add(*types)
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'Erro ao adicionar tipos para {spot.name}: {e}'))
        
        imported_count = TouristSpot.objects.filter(place_id__in=imported_place_ids).count()
        self.stdout.write(self.style.SUCCESS(f'Importação concluída! {imported_count} pontos turísticos importados.'))