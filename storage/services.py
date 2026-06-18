from datetime import timedelta
from .models import (
    GrainType, Granary, TemperatureHumidityLog,
    VentilationLog, PestInspection, RiskAssessment
)


class RiskCalculator:
    MOLD_WEIGHT = 0.6
    PEST_WEIGHT = 0.4
    LOW_RISK_THRESHOLD = 30
    HIGH_RISK_THRESHOLD = 70

    @classmethod
    def calculate_mold_risk(cls, granary, assess_date):
        grain_type = granary.grain_type
        temp_min = grain_type.safe_temp_min
        temp_max = grain_type.safe_temp_max
        hum_min = grain_type.safe_humidity_min
        hum_max = grain_type.safe_humidity_max

        recent_logs = TemperatureHumidityLog.objects.filter(
            granary=granary,
            record_date__lte=assess_date,
            record_date__gte=assess_date - timedelta(days=6)
        ).order_by('-record_date')

        if not recent_logs:
            return 0.0, 0

        temp_scores = []
        hum_scores = []
        exceed_days = 0

        for log in recent_logs:
            temp_dev = 0
            if log.temperature > temp_max:
                temp_dev = min((log.temperature - temp_max) * 5, 50)
                exceed_days += 1
            elif log.temperature < temp_min:
                temp_dev = min((temp_min - log.temperature) * 3, 30)
                exceed_days += 1
            temp_scores.append(temp_dev)

            hum_dev = 0
            if log.humidity > hum_max:
                hum_dev = min((log.humidity - hum_max) * 4, 50)
                if log.humidity > hum_max and exceed_days <= len(recent_logs) - len(temp_scores) + 1:
                    pass
            elif log.humidity < hum_min:
                hum_dev = min((hum_min - log.humidity) * 1.5, 20)
            hum_scores.append(hum_dev)

        for log in recent_logs:
            if (log.temperature > temp_max or log.temperature < temp_min or
                    log.humidity > hum_max or log.humidity < hum_min):
                pass

        exceed_count = 0
        for log in recent_logs:
            is_exceed = (log.temperature > temp_max or log.temperature < temp_min or
                         log.humidity > hum_max or log.humidity < hum_min)
            if is_exceed:
                exceed_count += 1

        avg_temp_score = sum(temp_scores) / len(temp_scores) if temp_scores else 0
        avg_hum_score = sum(hum_scores) / len(hum_scores) if hum_scores else 0

        base_score = avg_temp_score * 0.5 + avg_hum_score * 0.5

        exceed_bonus = (exceed_count / len(recent_logs)) * 20

        sensitivity_factor = grain_type.mold_sensitivity

        ventilation_factor = RiskAssessment.calculate_ventilation_factor(granary, assess_date)

        mold_score = (base_score + exceed_bonus) * sensitivity_factor * ventilation_factor
        mold_score = max(0.0, min(100.0, round(mold_score, 2)))

        return mold_score, exceed_count

    @classmethod
    def calculate_pest_risk(cls, granary, assess_date):
        grain_type = granary.grain_type

        recent_inspection = PestInspection.objects.filter(
            granary=granary,
            inspect_date__lte=assess_date,
            inspect_date__gte=assess_date - timedelta(days=14)
        ).order_by('-inspect_date').first()

        recent_log = TemperatureHumidityLog.objects.filter(
            granary=granary,
            record_date__lte=assess_date
        ).order_by('-record_date').first()

        if not recent_inspection:
            return 0.0

        density = recent_inspection.pest_density

        density_score = 0
        if density >= 10:
            density_score = 80
        elif density >= 5:
            density_score = 60
        elif density >= 2:
            density_score = 40
        elif density >= 1:
            density_score = 25
        elif density > 0:
            density_score = 10

        temp_factor = 1.0
        if recent_log:
            temp = recent_log.temperature
            if 25 <= temp <= 35:
                temp_factor = 1.5
            elif 20 <= temp < 25 or 35 < temp <= 38:
                temp_factor = 1.2
            elif temp < 15 or temp > 40:
                temp_factor = 0.6

        sensitivity_factor = grain_type.pest_sensitivity

        ventilation_factor = RiskAssessment.calculate_ventilation_factor(granary, assess_date)

        pest_score = density_score * temp_factor * sensitivity_factor * ventilation_factor
        pest_score = max(0.0, min(100.0, round(pest_score, 2)))

        return pest_score

    @classmethod
    def calculate_overall_risk(cls, mold_score, pest_score):
        overall = mold_score * cls.MOLD_WEIGHT + pest_score * cls.PEST_WEIGHT
        return round(overall, 2)

    @classmethod
    def determine_risk_level(cls, overall_score):
        if overall_score < cls.LOW_RISK_THRESHOLD:
            return 'low'
        elif overall_score < cls.HIGH_RISK_THRESHOLD:
            return 'medium'
        else:
            return 'high'

    @classmethod
    def assess_granary(cls, granary, assess_date):
        consecutive_days = granary.get_consecutive_days()
        has_continuous = granary.has_continuous_data(days=3)

        mold_score, _ = cls.calculate_mold_risk(granary, assess_date)
        pest_score = cls.calculate_pest_risk(granary, assess_date)
        ventilation_factor = RiskAssessment.calculate_ventilation_factor(granary, assess_date)
        overall_score = cls.calculate_overall_risk(mold_score, pest_score)
        risk_level = cls.determine_risk_level(overall_score)

        assessment = RiskAssessment(
            granary=granary,
            assess_date=assess_date,
            mold_risk_score=mold_score,
            pest_risk_score=pest_score,
            ventilation_factor=ventilation_factor,
            overall_risk_score=overall_score,
            risk_level=risk_level,
            is_formal=has_continuous,
            consecutive_days=consecutive_days,
        )
        return assessment

    @classmethod
    def assess_all_granaries(cls, assess_date):
        granaries = Granary.objects.filter(is_active=True)
        assessments = []
        for granary in granaries:
            assessment = cls.assess_granary(granary, assess_date)
            assessments.append(assessment)
        RiskAssessment.objects.bulk_create(assessments)
        return assessments


def recalculate_risks_after_ventilation(ventilation_log):
    granary = ventilation_log.granary
    end_date = ventilation_log.end_time.date() if ventilation_log.end_time else ventilation_log.start_time.date()

    existing = RiskAssessment.objects.filter(
        granary=granary,
        assess_date__gte=end_date - timedelta(days=3),
        assess_date__lte=end_date
    )

    for assessment in existing:
        mold_score, _ = RiskCalculator.calculate_mold_risk(granary, assessment.assess_date)
        pest_score = RiskCalculator.calculate_pest_risk(granary, assessment.assess_date)
        ventilation_factor = RiskAssessment.calculate_ventilation_factor(granary, assessment.assess_date)
        overall_score = RiskCalculator.calculate_overall_risk(mold_score, pest_score)
        risk_level = RiskCalculator.determine_risk_level(overall_score)

        assessment.mold_risk_score = mold_score
        assessment.pest_risk_score = pest_score
        assessment.ventilation_factor = ventilation_factor
        assessment.overall_risk_score = overall_score
        assessment.risk_level = risk_level
        assessment.save()

    return existing.count()
