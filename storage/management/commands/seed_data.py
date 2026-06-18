from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta, datetime
import random

from storage.models import (
    GrainType, Granary, TemperatureHumidityLog,
    VentilationLog, PestInspection, InventoryChangeLog,
    GrainSituationPrediction, AllocationConfig, AllocationSuggestion,
    AllocationExecution
)
from storage.services import GrainSituationPredictionService, AllocationService, InventoryService
from storage.services import RiskCalculator


class Command(BaseCommand):
    help = '初始化粮仓风险监测系统的测试数据'

    def handle(self, *args, **options):
        self.stdout.write('开始初始化测试数据...')

        grain_types_data = [
            {'name': '小麦', 'safe_temp_min': 10, 'safe_temp_max': 25,
             'safe_humidity_min': 55, 'safe_humidity_max': 75,
             'mold_sensitivity': 1.0, 'pest_sensitivity': 1.1,
             'description': '主要粮食作物，冬小麦耐热性较好'},
            {'name': '稻谷', 'safe_temp_min': 10, 'safe_temp_max': 22,
             'safe_humidity_min': 50, 'safe_humidity_max': 70,
             'mold_sensitivity': 1.3, 'pest_sensitivity': 1.2,
             'description': '易吸湿返潮，对温湿度要求较高'},
            {'name': '玉米', 'safe_temp_min': 10, 'safe_temp_max': 28,
             'safe_humidity_min': 55, 'safe_humidity_max': 78,
             'mold_sensitivity': 1.2, 'pest_sensitivity': 1.3,
             'description': '胚大吸湿性强，易生虫霉变'},
            {'name': '大豆', 'safe_temp_min': 8, 'safe_temp_max': 23,
             'safe_humidity_min': 50, 'safe_humidity_max': 68,
             'mold_sensitivity': 1.1, 'pest_sensitivity': 0.9,
             'description': '高油高蛋白，高温易走油'},
            {'name': '高粱', 'safe_temp_min': 10, 'safe_temp_max': 26,
             'safe_humidity_min': 55, 'safe_humidity_max': 75,
             'mold_sensitivity': 0.9, 'pest_sensitivity': 1.0,
             'description': '耐储性较好'},
        ]
        grain_types = []
        for gt in grain_types_data:
            obj, created = GrainType.objects.get_or_create(name=gt['name'], defaults=gt)
            grain_types.append(obj)
        self.stdout.write(self.style.SUCCESS(f'  粮食品类: {len(grain_types)} 种'))

        granary_data = [
            {'code': 'A-01', 'name': '一号平房仓', 'capacity': 2500, 'current_stock': 2200,
             'grain_type': grain_types[0], 'location': '东区A排1号', 'ventilation_status': 'closed'},
            {'code': 'A-02', 'name': '二号平房仓', 'capacity': 2500, 'current_stock': 1800,
             'grain_type': grain_types[1], 'location': '东区A排2号', 'ventilation_status': 'natural'},
            {'code': 'A-03', 'name': '三号平房仓', 'capacity': 3000, 'current_stock': 2800,
             'grain_type': grain_types[2], 'location': '东区A排3号', 'ventilation_status': 'mechanical'},
            {'code': 'B-01', 'name': '四号立筒仓', 'capacity': 1500, 'current_stock': 1450,
             'grain_type': grain_types[3], 'location': '西区B排1号', 'ventilation_status': 'closed'},
            {'code': 'B-02', 'name': '五号立筒仓', 'capacity': 1500, 'current_stock': 1200,
             'grain_type': grain_types[4], 'location': '西区B排2号', 'ventilation_status': 'natural'},
            {'code': 'C-01', 'name': '六号浅圆仓', 'capacity': 4000, 'current_stock': 3500,
             'grain_type': grain_types[0], 'location': '南区C排1号', 'ventilation_status': 'closed'},
            {'code': 'C-02', 'name': '七号浅圆仓', 'capacity': 4000, 'current_stock': 3800,
             'grain_type': grain_types[1], 'location': '南区C排2号', 'ventilation_status': 'mechanical'},
            {'code': 'C-03', 'name': '八号浅圆仓', 'capacity': 4000, 'current_stock': 0,
             'grain_type': grain_types[2], 'location': '南区C排3号', 'ventilation_status': 'closed',
             'is_active': True},
        ]
        granaries = []
        for gd in granary_data:
            obj, created = Granary.objects.get_or_create(code=gd['code'], defaults=gd)
            granaries.append(obj)
        self.stdout.write(self.style.SUCCESS(f'  粮仓: {len(granaries)} 个'))

        today = date.today()
        th_count = 0
        for g in granaries:
            gt = g.grain_type
            for day_offset in range(29, -1, -1):
                d = today - timedelta(days=day_offset)
                base_temp = random.uniform(gt.safe_temp_min - 2, gt.safe_temp_max + 8)
                base_hum = random.uniform(gt.safe_humidity_min - 3, gt.safe_humidity_max + 6)
                if g.code == 'C-01':
                    base_temp += random.uniform(3, 6)
                    base_hum += random.uniform(3, 8)
                if g.code == 'A-03':
                    base_temp -= random.uniform(0, 2)
                    base_hum -= random.uniform(2, 5)
                TemperatureHumidityLog.objects.get_or_create(
                    granary=g, record_date=d,
                    defaults={
                        'temperature': round(base_temp, 1),
                        'humidity': round(base_hum, 1),
                        'recorder': random.choice(['张工', '李工', '王工', '赵工']),
                    }
                )
                th_count += 1
        self.stdout.write(self.style.SUCCESS(f'  温湿度记录: {th_count} 条'))

        vent_count = 0
        for g in granaries:
            if g.ventilation_status != 'closed':
                for i in range(2):
                    days_ago = random.choice([1, 2, 3, 5, 7])
                    start_hour = random.randint(18, 23)
                    duration = random.choice([2, 4, 6, 8, 10])
                    start = datetime.combine(today - timedelta(days=days_ago), datetime.min.time()) + timedelta(hours=start_hour)
                    end = start + timedelta(hours=duration)
                    VentilationLog.objects.get_or_create(
                        granary=g, start_time=start,
                        defaults={
                            'end_time': end,
                            'ventilation_type': g.ventilation_status if g.ventilation_status in ['natural', 'mechanical'] else 'natural',
                            'operator': random.choice(['张工', '李工', '王工']),
                            'before_temp': round(random.uniform(20, 30), 1),
                            'before_humidity': round(random.uniform(60, 80), 1),
                            'after_temp': round(random.uniform(15, 22), 1),
                            'after_humidity': round(random.uniform(55, 68), 1),
                        }
                    )
                    vent_count += 1
        self.stdout.write(self.style.SUCCESS(f'  通风记录: {vent_count} 条'))

        pest_count = 0
        pest_type_choices = ['玉米象', '谷蠹', '赤拟谷盗', '麦蛾', '书虱', '螨虫']
        for g in granaries:
            for day_offset in [0, 7, 14, 21]:
                d = today - timedelta(days=day_offset)
                if g.code == 'C-01':
                    density = round(random.uniform(2, 12), 1)
                elif g.code == 'B-02':
                    density = round(random.uniform(0, 3), 1)
                else:
                    density = round(random.uniform(0, 1.5), 1)
                PestInspection.objects.get_or_create(
                    granary=g, inspect_date=d,
                    defaults={
                        'pest_density': density,
                        'pest_type': random.choice(pest_type_choices) if density > 0 else '',
                        'sample_points': random.randint(3, 8),
                        'inspector': random.choice(['张工', '李工', '王工', '赵工']),
                    }
                )
                pest_count += 1
        self.stdout.write(self.style.SUCCESS(f'  虫害抽检: {pest_count} 条'))

        risk_count = 0
        for day_offset in range(29, -1, -1):
            d = today - timedelta(days=day_offset)
            for g in granaries:
                assess = RiskCalculator.assess_granary(g, d)
                from storage.models import RiskAssessment
                existing = RiskAssessment.objects.filter(granary=g, assess_date=d).first()
                if existing:
                    existing.mold_risk_score = assess.mold_risk_score
                    existing.pest_risk_score = assess.pest_risk_score
                    existing.ventilation_factor = assess.ventilation_factor
                    existing.overall_risk_score = assess.overall_risk_score
                    existing.risk_level = assess.risk_level
                    existing.is_formal = assess.is_formal
                    existing.consecutive_days = assess.consecutive_days
                    existing.save()
                else:
                    assess.save()
                risk_count += 1
        self.stdout.write(self.style.SUCCESS(f'  风险评估: {risk_count} 条'))

        self.stdout.write('  正在生成库存变动记录...')
        inv_count = 0
        for g in granaries:
            current_balance = g.current_stock
            for day_offset in range(29, -1, -1):
                d = today - timedelta(days=day_offset)
                if random.random() < 0.3:
                    change_type = random.choice(['in', 'out', 'in', 'out', 'adjust'])
                    if change_type == 'in':
                        qty = round(random.uniform(10, 100), 2)
                    elif change_type == 'out':
                        qty = -round(random.uniform(5, 80), 2)
                    else:
                        qty = round(random.uniform(-20, 20), 2)
                    
                    current_balance += qty
                    if current_balance < 0:
                        current_balance = 0
                    
                    InventoryChangeLog.objects.get_or_create(
                        granary=g, change_date=d, change_type=change_type,
                        defaults={
                            'grain_type': g.grain_type,
                            'quantity': qty,
                            'balance_after': current_balance,
                            'operator': random.choice(['张工', '李工', '王工', '赵工']),
                            'remark': random.choice(['日常出入库', '盘点调整', '采购入库', '销售出库', '']),
                        }
                    )
                    inv_count += 1
        self.stdout.write(self.style.SUCCESS(f'  库存变动记录: {inv_count} 条'))

        self.stdout.write('  正在生成调拨配置...')
        configs = []
        config_data = [
            {
                'name': '标准调拨策略', 'description': '默认调拨配置，平衡风险和库存',
                'is_default': True,
                'safety_stock_ratio': 30,
                'min_transfer_quantity': 50, 'max_transfer_quantity': 500,
                'priority_rule': 'balanced',
                'risk_weight': 0.4, 'inventory_weight': 0.4, 'distance_weight': 0.2,
                'high_risk_threshold': 7.0,
                'low_inventory_threshold': 20, 'high_inventory_threshold': 90,
                'allow_cross_grain_type': False,
                'auto_approve_below': 100,
            },
            {
                'name': '风险优先策略', 'description': '优先处理高风险粮仓',
                'is_default': False,
                'safety_stock_ratio': 25,
                'min_transfer_quantity': 30, 'max_transfer_quantity': 600,
                'priority_rule': 'risk_first',
                'risk_weight': 0.6, 'inventory_weight': 0.25, 'distance_weight': 0.15,
                'high_risk_threshold': 6.0,
                'low_inventory_threshold': 15, 'high_inventory_threshold': 95,
                'allow_cross_grain_type': False,
                'auto_approve_below': 150,
            },
        ]
        for cd in config_data:
            if cd['is_default']:
                AllocationConfig.objects.filter(is_default=True).update(is_default=False)
            obj, created = AllocationConfig.objects.get_or_create(
                name=cd['name'], defaults=cd
            )
            configs.append(obj)
        self.stdout.write(self.style.SUCCESS(f'  调拨配置: {len(configs)} 个'))

        self.stdout.write('  正在生成粮情预测...')
        pred_count = 0
        for horizon in [7, 14, 30]:
            for g in granaries:
                try:
                    pred = GrainSituationPredictionService.predict_granary(
                        granary=g,
                        prediction_date=today,
                        horizon_days=horizon
                    )
                    if pred:
                        pred_count += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'    生成{g.code}{horizon}天预测时出错: {e}'))
        self.stdout.write(self.style.SUCCESS(f'  粮情预测: {pred_count} 条'))

        self.stdout.write('  正在生成调拨建议...')
        try:
            suggestions = AllocationService.generate_allocation_suggestions(
                config=configs[0]
            )
            self.stdout.write(self.style.SUCCESS(f'  调拨建议: {len(suggestions)} 条'))
            
            for i, s in enumerate(suggestions):
                if i < 2 and s.status == 'pending':
                    s.status = 'approved'
                    s.approved_by = '系统自动'
                    s.approved_at = timezone.now()
                    s.approval_remark = '低于阈值自动批准'
                    s.save()
                    
                    exec_obj = AllocationService.create_execution(
                        suggestion=s,
                        operator='系统'
                    )
                    if exec_obj:
                        exec_obj.planned_date = today + timedelta(days=1)
                        exec_obj.save()
                        if i == 0:
                            exec_obj.status = 'in_transit'
                            exec_obj.actual_out_date = today
                            exec_obj.actual_quantity = s.suggested_quantity
                            exec_obj.out_operator = '张工'
                            exec_obj.transport_vehicle = '京A·12345'
                            exec_obj.out_remark = '出库正常'
                            exec_obj.save()
                        elif i == 1:
                            exec_obj.status = 'completed'
                            exec_obj.actual_out_date = today - timedelta(days=3)
                            exec_obj.actual_in_date = today
                            exec_obj.actual_quantity = s.suggested_quantity
                            exec_obj.received_quantity = s.suggested_quantity - round(random.uniform(0, 0.5), 2)
                            exec_obj.out_operator = '李工'
                            exec_obj.in_operator = '王工'
                            exec_obj.transport_vehicle = '京A·67890'
                            exec_obj.actual_cost = round(s.suggested_quantity * random.uniform(5, 15), 2)
                            exec_obj.out_remark = '出库正常'
                            exec_obj.in_remark = '入库验收完成'
                            exec_obj.completed_at = timezone.now()
                            exec_obj.save()
                            
                            InventoryService.create_change_log(
                                granary=exec_obj.source_granary,
                                change_type='transfer_out',
                                quantity=-exec_obj.actual_quantity,
                                grain_type=exec_obj.grain_type,
                                operator='王工',
                                remark='调拨出库',
                                related_allocation=exec_obj
                            )
                            InventoryService.create_change_log(
                                granary=exec_obj.target_granary,
                                change_type='transfer_in',
                                quantity=exec_obj.received_quantity,
                                grain_type=exec_obj.grain_type,
                                operator='王工',
                                remark='调拨入库',
                                related_allocation=exec_obj
                            )
                
                elif i < 4 and s.status == 'pending':
                    s.status = 'rejected'
                    s.approved_by = '管理员'
                    s.approved_at = timezone.now()
                    s.approval_remark = random.choice(['当前库存充足，暂不需要', '运输成本过高', '待进一步评估'])
                    s.save()
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'    生成调拨建议时出错: {e}'))

        self.stdout.write(self.style.SUCCESS('测试数据初始化完成！'))
