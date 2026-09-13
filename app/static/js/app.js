let currentChurch = "";


function openPage(id){

    document.querySelectorAll(".page")
    .forEach(page=>{
        page.classList.remove("active");
    });


    let page=document.getElementById(id);

    if(page){
        page.classList.add("active");
    }


    window.scrollTo(0,0);

}



function openChurch(name){

    currentChurch=name;

    let title=document.getElementById("churchName");

    if(title){
        title.innerText=name;
    }


    let visit=document.getElementById("visitChurch");

    if(visit){
        visit.innerText=
        "Вы выбрали домашнюю церковь: "+name;
    }


    openPage("detail");

}



function renderChurches(){

    let search=document
    .getElementById("search")
    .value
    .toLowerCase();


    document
    .querySelectorAll(".church-card")
    .forEach(card=>{


        let text=
        card.innerText.toLowerCase();


        if(text.includes(search)){
            card.style.display="block";
        }

        else{
            card.style.display="none";
        }


    });

}




function sendRequest(event){

    event.preventDefault();


    let name=
    document.getElementById("name").value;


    let telegram=
    document.getElementById("telegram").value;


    let message=
    document.getElementById("message").value;



    let data={

        church:currentChurch,

        name:name,

        telegram:telegram,

        message:message

    };



    console.log("Заявка:",data);



    // Telegram Web App

    if(window.Telegram &&
       Telegram.WebApp){


        Telegram.WebApp
        .sendData(
            JSON.stringify(data)
        );

    }



    openPage("success");


}



document.addEventListener(
"DOMContentLoaded",
()=>{


    if(window.Telegram &&
       Telegram.WebApp){

        Telegram.WebApp.ready();

    }


});