// A recent working view, not a rewrite of the owner's durable evidence.
const recentProgress=5, recentReceipts=5;
function progressView(entry){
 const {observation,...rest}=entry;
 return {...rest,...(observation?{observation_omitted:true}:{})};
}
function taskView(task){
 if(!task)return task;
 const {progress=[],last_observed,...rest}=task;
 const view={...rest,progress:progress.slice(-recentProgress).map(progressView),
  history_view:{retained_progress:progress.length,shown_progress:Math.min(progress.length,recentProgress),
   details:'Use observe(detail="full") for retained progress observations and action details. Summaries are reports, not proof of completion.'}};
 if(last_observed){
  const {recent_actions=[],...observation}=last_observed;
  view.last_observed={...observation,recent_action_count:recent_actions.length,
   action_details_omitted:recent_actions.length>0};
 }
 return view;
}
function eventView(event){
 // Human/peer text and its provenance stay intact, including authorization IDs.
 if(['chat','chat_sent'].includes(event.kind))return event;
 const {arguments:args,result,progress,observation,...rest}=event;
 return {...rest,...(progress?{progress:progressView(progress)}:{}),
  ...(result?{result_details_omitted:true,...(result.error?{error:result.error}:{})}:{}),
  ...(args?{argument_details_omitted:true}:{}),...(observation?{observation_omitted:true}:{})};
}
function worldView(state){
 const {task,events=[],receipts=[],public_chat,...current}=state;
 const messages=new Map((current.conversation?.messages||[]).map(m=>[m.id,m]));
 const compactEvents=events.map(event=>{
  const message=messages.get(event.id);
  // Drop only exactly duplicated text, not attribution/receipt facts or a
  // longer source whose conversational projection was truncated.
  if(event.kind==='chat'&&message?.text===event.message&&message?.author===event.username&&message?.time===event.time&&message?.source_fact?.id===event.id){
   const {message:text,...evidence}=event;
   return {...evidence,conversation_message_id:event.id};
  }
  return eventView(event);
 });
 return {...current,task:taskView(task),events:compactEvents,
  // Keep exact outcomes for recent actions; don't summarize uncertain effects as success.
  receipts:receipts.slice(-recentReceipts),
  history_view:{retained_receipts:receipts.length,shown_receipts:Math.min(receipts.length,recentReceipts),
   details:'Recent working view. Full retained evidence is available with observe(detail="full"). Public chat is in conversation. Missing older detail is not evidence that work succeeded or was handled.'}};
}
module.exports={taskView,worldView};
