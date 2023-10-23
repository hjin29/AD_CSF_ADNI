
import pickle
import re
import numpy as np
import pandas as pd
import warnings
from collections import Counter
from scipy.stats import ttest_ind, chi2_contingency, chisquare, entropy, pointbiserialr
from sklearn.metrics import brier_score_loss, recall_score, confusion_matrix, roc_auc_score, average_precision_score
from sklearn.metrics import log_loss, average_precision_score, f1_score
from itertools import product
import random
from sklearn.impute import SimpleImputer
from sklearn.impute import KNNImputer
from sklearn.experimental import enable_iterative_imputer
from sklearn.impute import IterativeImputer



def threshold(array, cutoff):
    array1 = array.copy()
    array1[array1 < cutoff] = 0
    array1[array1 >= cutoff] = 1
    return array1


def Youden_index(y_test, y_pred):
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
    sens = tp / (tp + fn)
    spec = tn / (tn + fp)
    return sens + spec - 1


def get_avg_score(pred_probs_list, y_test_list, optimal_cutoff):
    evaluations = []
    nb_folds = len(pred_probs_list)
    for i in range(nb_folds):
        pred_binary = threshold(pred_probs_list[i], optimal_cutoff)
        tn, fp, fn, tp = confusion_matrix(y_test_list[i], pred_binary).ravel()
        acc  = (tp + tn) / (tp + tn + fp +fn)
        sens = tp / (tp + fn)
        spec = tn / (tn + fp)
        prec = tp / (tp + fp)
        Youden = sens + spec - 1
        f1 = 2 * prec * sens / (prec + sens)
        auc = roc_auc_score(y_test_list[i], pred_probs_list[i])
        apr = average_precision_score(y_test_list[i], pred_probs_list[i])
        evaluations.append([acc, sens, spec, prec, Youden, f1, auc, apr])
    eval_avg = np.round(np.average(np.array(evaluations), axis = 0), 4).tolist()
    eval_std = np.round(np.std(np.array(evaluations), axis = 0), 4).tolist()
    return (eval_avg, eval_std)


def my_imputer(method = 'MEAN'):
    if method == 'MEAN':
        imputer = SimpleImputer(missing_values = np.nan, strategy = 'mean')
    elif method == 'MEDIAN':
        imputer = SimpleImputer(missing_values = np.nan, strategy = 'median')
    elif method == 'KNN':
        imputer = KNNImputer(n_neighbors = 10, weights = 'uniform')
    elif method == 'MICE':
        imputer = IterativeImputer(max_iter = 10, random_state = 2020)
    return imputer


def Randomized_cv(selected_params, imp_method, mykf, X, y):
    AUC_cv = []
    for train_idx, test_idx in mykf.split(X, y):
        X_train, X_test = X.iloc[train_idx,:], X.iloc[test_idx,:]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
        under = RandomUnderSampler(sampling_strategy = 1, random_state = 2020)
        X_train, y_train = under.fit_resample(X_train, y_train)
        imputer = my_imputer(method = imp_method)
        X_train = imputer.fit_transform(X_train)
        X_test = imputer.transform(X_test)
        AUC_list = []
        for my_params in selected_params:
            my_clf = LogisticRegression()
            my_clf.set_params(**my_params)
            my_clf.fit(X_train, y_train)
            y_pred_prob = my_clf.predict_proba(X_test)[:, 1]
            AUC_list.append(roc_auc_score(y_test, y_pred_prob))
        AUC_cv.append(AUC_list)
    AUC_cv = np.round(np.average(np.array(AUC_cv), axis = 0),4).tolist()
    index, best_auc = max(enumerate(AUC_cv), key = operator.itemgetter(1))
    best_params = selected_params[index]
    return((best_auc, best_params))


def get_full_eval(y_test, pred_prob, cutoff_list):
    evaluations = []
    for cutoff in cutoff_list:
        pred_binary = threshold(pred_prob, cutoff)
        tn, fp, fn, tp = confusion_matrix(y_test, pred_binary).ravel()
        acc  = (tp+tn)/ (tp + tn + fp +fn)
        sens = tp / (tp + fn)
        spec = tn / (tn + fp)
        prec = tp / (tp + fp)
        Youden = sens + spec - 1
        f1 = 2*prec*sens/(prec + sens)
        auc = roc_auc_score(y_test, pred_prob)
        apr = average_precision_score(y_test, pred_prob)
        nnd = 1/Youden
        evaluations.append(np.round((cutoff, acc, sens, spec, prec, Youden, f1, auc, apr, nnd), 4))
    evaluations = pd.DataFrame(evaluations)
    evaluations.columns = ['Cutoff', 'Acc', 'Sens', 'Spec', 'Prec', 'Youden', 'F1', 'AUC', 'APR', 'NND']
    return evaluations


def avg_results(results_list):
    col_names = results_list[0].columns.tolist()
    col_names_std = [item + '_std' for item in col_names]
    nb_fold, nb_row, nb_col = len(results_list), results_list[0].shape[0], results_list[0].shape[1]
    results = np.zeros((nb_fold, nb_row, nb_col))
    for i in range(nb_fold):
        results[i] = np.array(results_list[i])
    results_avg = pd.DataFrame(np.round(np.average(results, axis = 0),3), columns = col_names)
    results_std = pd.DataFrame(np.round(np.std(results, axis = 0), 3), columns = col_names_std)
    return pd.concat((results_avg, results_std), axis = 1)


def autolabel(rects, ax, x_move):
    """Attach a text label above each bar in *rects*, displaying its height."""
    for rect in rects:
        height = rect.get_height()
        ax.annotate('{}'.format(height),
                    xy=(rect.get_x() + rect.get_width() / 2 + x_move, height),
                    xytext=(0, 3),  # 3 points vertical offset
                    textcoords="offset points",
                    ha='center', va='bottom')

def match_labels(f_lst, f_dict):
    f_df = pd.DataFrame({'Features':f_lst})
    merged_df = pd.merge(f_df, f_dict, how='inner', on=['Features'])
    return merged_df['Field']



def get_opt_ct(mydf, target_y, y_pred_col):
    Youden_cv = [Youden_index(mydf[target_y], threshold(mydf[y_pred_col], i*0.001)) for i in range(200)]
    opt_ct_idx = Youden_cv.index(np.max(Youden_cv))
    opt_ct = 0.001*(opt_ct_idx+1)
    return opt_ct

def get_eval(y_test, pred_prob, cutoff):
    pred_binary = threshold(pred_prob, cutoff)
    tn, fp, fn, tp = confusion_matrix(y_test, pred_binary).ravel()
    acc = (tp + tn) / (tp + tn + fp + fn)
    sens = tp / (tp + fn)
    spec = tn / (tn + fp)
    prec = tp / (tp + fp)
    Youden = sens + spec - 1
    f1 = 2 * prec * sens / (prec + sens)
    auc = roc_auc_score(y_test, pred_prob)
    apr = average_precision_score(y_test, pred_prob)
    brier = brier_score_loss(y_test, pred_prob)
    nnd = 1 / Youden
    evaluations = np.round((cutoff, acc, sens, spec, prec, Youden, f1, auc, apr, nnd, brier), 4)
    evaluations = pd.DataFrame(evaluations).T
    evaluations.columns = ['Cutoff', 'Acc', 'Sens', 'Spec', 'Prec', 'Youden', 'F1', 'AUC', 'APR', 'NND', 'BRIER']
    evaluations = evaluations[['Cutoff', 'Acc', 'Sens', 'Spec', 'Prec', 'Youden', 'F1', 'AUC', 'APR', 'NND', 'BRIER']]
    return evaluations

def get_bt_output(mydf, y_true_col, y_pred_col, nb_iters, cutoff, incident):
    tmpout_df, result_df = pd.DataFrame(), pd.DataFrame()
    idx_lst = [ele for ele in range(len(mydf))]
    for i in range(nb_iters):
        random.seed(i)
        bt_idx = [random.choice(idx_lst) for _ in range(len(idx_lst))]
        mydf_bt = mydf.copy()
        mydf_bt = mydf_bt.iloc[bt_idx, :]
        mydf_bt.reset_index(inplace = True, drop = True)
        y_test, pred_prob = mydf_bt[y_true_col], mydf_bt[y_pred_col]
        tmp_result_df = get_eval(y_test, pred_prob, cutoff)
        tmpout_df = pd.concat([tmpout_df, tmp_result_df], axis = 0)
    tmpout_df.reset_index(inplace = True, drop = True)
    rm_idx = tmpout_df.index[tmpout_df.AUC < 0.5]
    tmpout_df.drop(rm_idx, axis = 0, inplace = True)
    tmpout_df.reset_index(inplace = True, drop = True)
    median_df = tmpout_df.median(axis = 0)
    lbd_df = tmpout_df.quantile(0.025, axis = 0)
    ubd_df = tmpout_df.quantile(0.975, axis = 0)
    result_df = pd.concat([median_df, lbd_df, ubd_df], axis=1)
    result_df.columns = [incident + '_median', incident + '_lbd', incident+ '_ubd']
    out_lst = []
    for i in range(11):
        tmp_median = f'{result_df.iloc[i, 0]:.3f}'
        tmp_lbd = f'{result_df.iloc[i, 1]:.3f}'
        tmp_ubd = f'{result_df.iloc[i, 2]:.3f}'
        out_lst.append(tmp_median + ' [' + tmp_lbd + ', ' + tmp_ubd + ']')
    result_df[incident] = out_lst
    print('Done ' + incident)
    return result_df.T
