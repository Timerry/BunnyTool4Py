import { createStore, applyMiddleware, compose } from 'redux';
import thunk from 'redux-thunk';
import { createHashHistory } from 'history';
import { routerMiddleware, connectRouter } from 'connected-react-router';
import rootReducer from '../reducers/index';

const history = createHashHistory();
const router = routerMiddleware(history);
const enhancer = applyMiddleware(thunk, router);

function configureStore(initialState) {
  return createStore(connectRouter(history)(rootReducer), initialState, enhancer);
}

export default { configureStore, history };
