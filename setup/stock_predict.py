from helpers import *
from datetime import *

MODEL_ORDERS = ((1,0,0), (1, 1, 1, 7))

'''
When prediction runs, will send data to firebase + graph.
App should hook into changes to prediction and update.
'''

# predicts and sends graphs + data to firestore
def stock_predict(db):
    now = date.today()

    # -- MAKE PREDICTIONS -- #

    historical_window, prediction_window = fetch_params(db)

    query_from = format_date(now - timedelta(days=historical_window))
    curr_date = format_date(now)

    docs = db.collection(u'consumption').where(u'timestamp', u'>=', query_from).where(u'timestamp', u'<', curr_date).stream()

    apple_data, banana_data, egg_data = [], [], []
    for doc in docs:
        counts = doc.to_dict()
        apple_data.append(counts['apple'])
        banana_data.append(counts['banana'])
        egg_data.append(counts['egg'])

    assert(len(apple_data) > 7, 'Not enough consumption data!')

    predict_for_item(db, apple_data, prediction_window, 'apple', now)
    predict_for_item(db, banana_data, prediction_window, 'banana', now)
    predict_for_item(db, egg_data, prediction_window, 'egg', now)

def fetch_params(db):
    # fetch prediction parameters from firebase
    config = db.collection('config').document('config').get()
    if config.exists:
        conf = config.to_dict()
        return conf['historical_window'], conf['prediction_window']
    else:
        return 60, 7 # default, in case config doesn't exist

# predicts and saves to firebase for item
def predict_for_item(db, data, prediction_window, item, now):
    predicted = SARIMA_PREDICT(data, orders=MODEL_ORDERS, num_predict=prediction_window)

    graph_img = DISPLAY_DATA(now, data, predicted, item_name=item)

    doc_ref = db.collection('predict').document(item)
    doc_ref.set({
        'historical_data': list(data),
        'predicted_data': predicted.tolist(),
        'graph_img_base64': graph_img,
    })
