import pandas as pd
import numpy as np
from sklearn.svm import SVR
from auxiliary_funcs import *
from plot_funcs import *



def find_period_not_equidist(path, 
reference_time,
tol_norm_diff=10**(-3), 
number_steps=1000,
minimum_number_of_relevant_shifts=2,
minimum_number_of_datapoints_for_correlation_test=300,
minimum_ratio_of_datapoints_for_shift_autocorrelation=0.3,
consider_only_significant_correlation=1,
level_of_significance_for_pearson=0.01,
output_flag=1,
plot_tolerances=1):
    '''
    This is the main period detection function. 
    It reads your timeseries from a file given as path and calculates the difference between the original autocorrelation function and several possible shifts in order to find minima which indicate possible periods.
    Then a model is fitted for every suggested period. Afterwards each models performance is evaluated by taking the original time series and subtracting the model. 
    If the model fits the time series well, the leftover should be noise and the autocorrelation function should deteriorate.
    It requires the data path, 
    a reference time for shift/phase calculation and relevant when fitting the model reference_time,
    the tolerance for the norm difference between the unshifted and shifted autocorrelation function for a shift tol_norm_diff,
    the number of times iteratively we increase the tolerance number_steps,
    the minimum number of shifts required for calculation minimum_number_of_relevant_shifts,
    the minimum number of datapoints required for calculation minimum_number_of_datapoints_for_correlation_test,
    the minimum ratio of datapoints for which we calculate the autocorrelation of a shift minimum_ratio_of_datapoints_for_shift_autocorrelation,
    the flag declaring the usage only of correlations matching our criterion consider_only_significant_correlation,
    the minimum significance level for our correlation criterion level_of_significance_for_pearson,
    the output flag setting plotting to on/off output_flag,
    the output flag allowing tolerances to be plotted plot_tolerances.
    The returns are the resulting period res_period, the fitted model res_model if a period was found and a performance criterion res_criteria

    :param path: string
    :param reference_time: pd.Timestamp
    :param tol_norm_diff: positive float
    :param number_steps: positive integer
    :param minimum_number_of_datapoints_for_correlation_test: positive integer
    :param minimum_ratio_of_datapoints_for_shift_autocorrelation: positive float
    :param consider_only_significant_correlation: Boolean
    :param level_of_significance_for_pearson: positive float
    :param output_flag: Boolean
    :param plot_tolerances: Boolean
    :return: positive float, RandomForestRegressor (optional), positive float
    '''

    # Load data
    df_data_aggregated = pd.read_csv(path, parse_dates=["date"])
    
    # Calculate the autocorrelation function and receive the correlation values r_list, the level of significance list p_list (Step 2 in Algorithm 1 in the paper)
    r_list, p_list, corfunc, lag_list = autocor(df_data_aggregated["value"], list(range(0,int((df_data_aggregated["value"].size)-minimum_number_of_datapoints_for_correlation_test))), level_of_significance_for_pearson,consider_only_significant_correlation)

    # Test the datapoints for equidistance
    pw_dist = [y-x for x,y in zip(*[iter(df_data_aggregated["date"])]*2)]
    if max(pw_dist) == min(pw_dist):
        print("Equidistant datapoints.")
    else:
        print("The datapoints are not equidistant!")
    
    # Calculate the difference between the unshifted and shifted autocorrelation function for each shift and determine which ones are relevant based on their local minima (Step 3 & 4 in Algorithm 1 in the paper)
    diffs = [shift_diff(i, corfunc) for i in list(range(0,int(np.array(corfunc).size-np.array(corfunc).size*minimum_ratio_of_datapoints_for_shift_autocorrelation)))]
    relevant_diffs, peaks, stop_calculation = get_relevant_diffs(diffs)

    list_relv_pos=[]
    size_list_relv_pos=len(list_relv_pos)

    list_suggested_periods=[]
    list_criterion=[]
    list_norms_data_model=[]
    list_norm_diff_data_model=[]
    list_model_data=[]
    list_tolerances=[]
    list_models=[]
    if stop_calculation == 0:
        sum_of_shifted_correlation_function = [sum_shifted_function(i, corfunc) for i in list(peaks)]
        df_diffs_lag = pd.DataFrame({'lags': peaks, 'diffs': relevant_diffs, 'sum_of_norms': sum_of_shifted_correlation_function})

        # Step by step extend the set of considered shifts (Step 5 in Algorithm 1 in the paper)
        for tol_for_zero in np.linspace(0,1,number_steps+1):
            # Filter for shifts smaller or equal to our criterion tol_for_zero (Step 5 a) in the paper)
            vec_bool=(df_diffs_lag['diffs']<=tol_for_zero) & (df_diffs_lag['sum_of_norms']>tol_for_zero)
            list_relv_pos=(df_diffs_lag['lags'][vec_bool]).to_list()
            
            # If we have no (further) relevant shifts, we can abort (Step 5 b) in Algorithm 1 in the paper)
            if len(list_relv_pos) >= minimum_number_of_relevant_shifts and len(list_relv_pos)>size_list_relv_pos:
                size_list_relv_pos = len(list_relv_pos)
                correlationvalues_at_relevant_peaks = np.array(corfunc)[np.array(list_relv_pos)]
                all_relv_pos_with_positive_correlation = sum((correlationvalues_at_relevant_peaks <= 0).astype(int)) <= 0
                if all_relv_pos_with_positive_correlation==True:
                    list_tolerances.append(tol_for_zero)
                    # Get the time difference between the shifts (Step 5 c) in Algorithm 1 in the paper)...
                    relv_time_diff=((df_data_aggregated["date"].iloc[list_relv_pos]-df_data_aggregated["date"].iloc[0]) / pd.Timedelta('1 minutes')).to_list()
                    list_of_periods=np.diff(np.array(relv_time_diff))
                    # ...and calculate their median as suggested period (Step 5 d) in Algorithm 1 in the paper)
                    suggested_period = np.median(np.array(list_of_periods)) 
                    suggested_period_in_unit_of_duration_lag=suggested_period 

                    # Fit a model based on the data and the phase inside the period, here calculated using modulo (Step 5 e) in Algorithm 1 in the paper)
                    df_data_aggregated['date_modulo']=(((df_data_aggregated["date"] - reference_time) / pd.Timedelta('1 minutes')) % suggested_period_in_unit_of_duration_lag).copy()
                    model_data,mlp= fit_model(df_data_aggregated)

                    # Subtract the model data from the original and determine the autocorrelation function as a performance measure (Step 5 f) & g) in Algorithm 1 in the paper)
                    signal_data=df_data_aggregated["value"].to_numpy().reshape(df_data_aggregated["value"].size, 1)
                    signal_subtracted_model = signal_data - model_data
                    df_data_difference_signal_model = pd.DataFrame(data=signal_subtracted_model, columns=["value"])
                    if output_flag==1:
                        r_list_diff, p_list_diff, corfunc_diff, lag_list_diff = autocor(df_data_difference_signal_model["value"], list(range(0,int((df_data_difference_signal_model["value"].size)-minimum_number_of_datapoints_for_correlation_test))),level_of_significance_for_pearson,consider_only_significant_correlation)
                        correlationvalues_signalModel_at_relevant_peaks=np.array(corfunc_diff)[np.array(list_relv_pos)]
                    else:
                        r_list_diff, p_list_diff, cor_func_diff, lag_list_diff = autocor(df_data_difference_signal_model["value"], list_relv_pos, level_of_significance_for_pearson,consider_only_significant_correlation)
                        correlationvalues_signalModel_at_relevant_peaks=np.array(cor_func_diff)
                    reduction_of_correlation = 1 - abs(correlationvalues_signalModel_at_relevant_peaks[1:]).mean() / abs(correlationvalues_at_relevant_peaks[1:]).mean()

                    list_suggested_periods.append(suggested_period)
                    list_criterion.append(reduction_of_correlation)
                    list_model_data.append(model_data)
                    list_models.append(mlp)
                    norm_signal = sum(abs(signal_data))[0] / signal_data.size
                    norm_model = sum(abs(model_data))[0] / model_data.size
                    list_norms_data_model.append(norm_signal + norm_model)
                    norm_diff_between_singal_and_model = sum(abs(signal_subtracted_model))[0] / signal_subtracted_model.size
                    list_norm_diff_data_model.append(norm_diff_between_singal_and_model)
                else:
                    print('Relevant lag in autocorrelation function with non-positive correlation!')
                    break

        # Check if there are any suggested periods left if yes... (Step 6 in Algorithm 1 in the paper)      
        if len(list_suggested_periods)>0:
            df_periods_criterion=pd.DataFrame({'periods':list_suggested_periods, 'criterion':list_criterion, 'norm_diff':list_norm_diff_data_model ,'sum_norms':list_norms_data_model, 'model_data':list_model_data, 'models':list_models, 'tolerances':list_tolerances})
            period_very_close_fit=df_periods_criterion['periods'][(df_periods_criterion['norm_diff']<=tol_norm_diff) & (df_periods_criterion['sum_norms']>tol_norm_diff)]
            if period_very_close_fit.size>0:
                model_very_close_fit = df_periods_criterion['models'][(df_periods_criterion['norm_diff'] <= tol_norm_diff) & (df_periods_criterion['sum_norms'] > tol_norm_diff)]
                model_data_very_close_fit = df_periods_criterion['model_data'][(df_periods_criterion['norm_diff'] <= tol_norm_diff) & (df_periods_criterion['sum_norms'] > tol_norm_diff)]
                best_tolerances_close_fit = df_periods_criterion['tolerances'][(df_periods_criterion['norm_diff'] <= tol_norm_diff) & (df_periods_criterion['sum_norms'] > tol_norm_diff)]
                res_period=period_very_close_fit[0]
                res_model=model_very_close_fit[0]
                res_criteria=1.5
                model_data=model_data_very_close_fit[0]
                best_tolerance = best_tolerances_close_fit[0]
                other_tolerances = df_periods_criterion['tolerances'][df_periods_criterion['tolerances'] != best_tolerance].to_list()
                print('Very small difference between data and model, difference smaller than ' + str(tol_norm_diff))
                print('The suggested period in ' + 'in minutes is ' + str(res_period) + ', in hours is ' + str(res_period / 60) + ' and in days is ' + str(res_period / 60 / 24))
            else:
                index_min_criterion=df_periods_criterion['criterion'].idxmax()
                res_period=df_periods_criterion['periods'].iloc[index_min_criterion]
                res_criteria=df_periods_criterion['criterion'].iloc[index_min_criterion]
                res_model=df_periods_criterion['models'][index_min_criterion]
                model_data = df_periods_criterion['model_data'][index_min_criterion]
                best_tolerance=df_periods_criterion['tolerances'][index_min_criterion]
                other_tolerances=df_periods_criterion['tolerances'][df_periods_criterion.index != index_min_criterion].to_list()
                print('Reduction of correlation by model: ' + str(res_criteria) + ' with sigma ' + str(best_tolerance))
                print('The suggested period in ' + 'in minutes is ' + str(res_period) + ', in hours is ' + str(res_period / 60) + ' and in days is ' + str(res_period / 60 / 24))

            if output_flag==1:
                plot_with_period(df_data_aggregated, diffs, other_tolerances, best_tolerance, lag_list, r_list, p_list, corfunc, model_data, norm_diff_between_singal_and_model,  plot_tolerances,level_of_significance_for_pearson,consider_only_significant_correlation, minimum_number_of_datapoints_for_correlation_test)
        # If no, plot without period
        else:
            print('List of suggested periods is empty! Only correlation pattern in autocorrelation function found with at least one lag with zero correlation!')
            res_period = -1
            res_criteria = 0
            if output_flag == 1:
                plot_without_period(df_data_aggregated, diffs, lag_list, r_list, p_list, corfunc, plot_tolerances,level_of_significance_for_pearson,consider_only_significant_correlation, minimum_number_of_datapoints_for_correlation_test)
    else:
        res_period=-1
        res_criteria=0
        if output_flag==1:
            plot_without_period(df_data_aggregated, diffs, lag_list, r_list, p_list, corfunc)

            return res_period, res_criteria
    
    # return the period, the model and the criteria
    return res_period, res_model, res_criteria
